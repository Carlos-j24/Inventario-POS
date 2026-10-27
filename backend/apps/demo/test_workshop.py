"""Lo que deja sembrado `seed_demo --taller` (spec 009, T4). Se siembra una vez para todo el módulo."""
from decimal import Decimal

import pytest
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Product
from apps.customers.models import Customer
from apps.inventory.models import PhysicalCount, StockLevel, StockMovement, Transfer, Warehouse
from apps.invoicing.models import Business
from apps.reports.costs import inventory_report
from apps.sales.models import Order, Quote, Sale
from apps.workshop.models import Motorcycle

from .seed import USERS, seed

pytestmark = pytest.mark.django_db


@pytest.fixture(scope="module", autouse=True)
def seeded(django_db_setup, django_db_blocker):
    with django_db_blocker.unblock():
        atomic = transaction.atomic()
        atomic.__enter__()
        try:
            yield seed(password="Demo-clave-123", workshop=True)
        finally:
            transaction.set_rollback(True)
            atomic.__exit__(None, None, None)


def days_ago(when):
    return (timezone.localdate() - timezone.localtime(when).date()).days


def test_the_workshop_module_and_its_reception():
    business = Business.load()
    assert business.workshop_enabled is True
    assert (business.trade_name, business.check_digit) == ("Motos La 16", "6")
    diana = User.objects.get(username="diana.recepcion")
    assert [r.name for r in diana.roles.all()] == ["Recepción de taller"]
    assert diana.check_password("Demo-clave-123")


def test_the_same_users_as_the_hardware_store_plus_reception(seeded):
    assert set(seeded) == {u for u, *_ in USERS} | {"diana.recepcion"}


def test_motorcycle_parts_with_the_same_history():
    assert Product.objects.filter(sku="ACE-20W50", category__name="Lubricantes").exists()
    assert not Product.objects.filter(sku="CEM-50").exists()  # nada de ferretería
    pending = Product.objects.get(sku="DIR-LED")
    assert (pending.is_active, pending.price_pending) == (False, True)
    review = Sale.objects.get(needs_review=True)
    assert (review.offline, review.lines.get().product.sku) == (True, "ACE-20W50")
    assert Sale.objects.filter(status="VOIDED").count() == 1
    count = PhysicalCount.objects.get()
    assert (count.status, count.category.name) == ("APPROVED", "Lubricantes")
    assert count.lines.get(product__sku="ACE-10W40").difference == Decimal("-1.000")
    transfer = Transfer.objects.get()
    assert (transfer.destination.name, transfer.lines.get(product__sku="BOM-H4").base_quantity) == ("Mostrador del almacén", 10)
    assert Order.objects.get(status="PENDING").lines.filter(product__sku="LLA-90-18").exists()
    assert list(Warehouse.objects.filter(is_default=True).values_list("code", flat=True)) == ["PRAL"]
    statuses = sorted(q.effective_status() for q in Quote.objects.all())
    assert statuses == ["CONVERTED", "EXPIRED", "VALID", "VALID", "VOIDED"]


def test_the_kardex_matches_and_nothing_is_negative():
    for level in StockLevel.objects.select_related("product", "warehouse"):
        total = StockMovement.objects.filter(product=level.product, warehouse=level.warehouse).aggregate(q=Sum("quantity"))["q"]
        assert total == level.quantity, (level.product.sku, level.warehouse.code)
        assert level.quantity >= 0
    assert inventory_report()["totals"]["negative"] == 0
    # Las entradas a otro precio movieron el promedio del kit de arrastre y de la llanta trasera.
    for sku, first, later in (("KIT-BOX100", 64000, 69000), ("LLA-90-18", 98000, 104000)):
        assert StockLevel.objects.get(product__sku=sku, warehouse__code="PRAL").average_cost not in (Decimal(first), Decimal(later))


def test_customers_and_motorcycles_to_show():
    motos = {m.plate or m.vin: m for m in Motorcycle.objects.select_related("owner")}
    assert set(motos) == {"XYZ12A", "JKL90B", "ABC34D", "DEF56G", "9F2NKD125T0001234", "GHI78H"}
    assert all(m.owner.phone for m in motos.values())  # todo dueño tiene teléfono
    jorge = Customer.objects.get(name="Jorge Ramírez")
    assert set(jorge.motorcycles.values_list("plate", flat=True)) == {"XYZ12A", "JKL90B"}  # un cliente, dos motos
    assert motos["9F2NKD125T0001234"].plate == ""  # la nueva, sin placa


def test_mileage_readings_go_back_months():
    boxer = Motorcycle.objects.get(plate="XYZ12A")
    readings = list(boxer.mileage_readings.order_by("recorded_at"))
    assert [(r.mileage, days_ago(r.recorded_at)) for r in readings] == [(12500, 120), (14100, 35), (15200, 3)]
    assert (boxer.mileage, days_ago(boxer.mileage_at), days_ago(boxer.created_at)) == (15200, 3, 120)
    reset = Motorcycle.objects.get(plate="GHI78H").mileage_readings.order_by("-recorded_at").first()
    assert (reset.mileage, reset.previous, reset.note) == (120, 31200, "Cambio de tablero")


def test_one_motorcycle_changed_owner():
    honda = Motorcycle.objects.get(plate="DEF56G")
    current, previous = honda.ownerships.select_related("customer")
    assert (current.customer.name, current.ended_at) == ("Mensajería Express del Caquetá S.A.S.", None)
    assert previous.customer.name == "Luis Gómez"
    assert (days_ago(previous.started_at), days_ago(previous.ended_at), days_ago(current.started_at)) == (400, 30, 30)
    assert honda.owner == current.customer
