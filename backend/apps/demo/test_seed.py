"""Lo que deja sembrado seed_demo. Se siembra una vez para todo el módulo (tarda) y se deshace al final."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.accounts.models import User
from apps.cash.models import Shift
from apps.catalog.models import Product
from apps.inventory.models import Adjustment, PhysicalCount, StockLevel, StockMovement, Transfer
from apps.reports.costs import inventory_report
from apps.sales.models import Order, Sale, SaleReturn

from .seed import DAYS, USERS, seed

pytestmark = pytest.mark.django_db


@pytest.fixture(scope="module", autouse=True)
def seeded(django_db_setup, django_db_blocker):
    with django_db_blocker.unblock():
        atomic = transaction.atomic()
        atomic.__enter__()
        try:
            yield seed(password="Demo-clave-123")
        finally:
            transaction.set_rollback(True)
            atomic.__exit__(None, None, None)


def test_users_have_their_roles_and_the_given_password(seeded):
    assert set(seeded) == {username for username, *_ in USERS}
    for username, first_name, role in USERS:
        user = User.objects.get(username=username)
        assert user.check_password("Demo-clave-123")
        assert (user.first_name, [r.name for r in user.roles.all()]) == (first_name, [role])
    admin = User.objects.get(username="admin.demo")
    assert admin.is_superuser and admin.is_staff
    assert not User.objects.get(username="laura.caja").is_staff


def test_two_weeks_of_closed_shifts_and_one_open_today():
    today = timezone.localdate()
    expected_days = {
        today - timedelta(days=back) for back in range(1, DAYS + 1) if (today - timedelta(days=back)).weekday() != 6
    }  # un turno por día; los domingos no abre
    closed = Shift.objects.filter(status="CLOSED")
    assert {timezone.localtime(s.closed_at).date() for s in closed} == expected_days
    assert closed.count() == len(expected_days)
    assert closed.filter(difference=Decimal("-2000")).count() == 1  # el faltante del arqueo
    assert not closed.exclude(difference__in=[0, Decimal("-2000")]).exists()
    assert Shift.objects.filter(status="OPEN").count() == 1
    # Las ventas quedan en sus días, no todas hoy.
    assert {timezone.localtime(s.occurred_at).date() for s in Sale.objects.all()} == expected_days | {today}
    # También la fecha de registro (el admin de Django ordena por ella).
    assert all(s.created_at == s.occurred_at for s in Sale.objects.filter(offline=False))


def test_the_cases_worth_showing_are_there():
    assert Sale.objects.filter(status="VOIDED").count() == 1
    assert SaleReturn.objects.count() == 1
    review = Sale.objects.get(needs_review=True)  # solo la venta sin conexión con el precio viejo
    assert (review.offline, review.lines.get().product.sku) == (True, "PIN-VIN-B")
    assert set(Sale.objects.values_list("payments__method", flat=True)) == {"CASH", "CARD", "TRANSFER"}
    assert Order.objects.get().status == "PENDING"
    assert set(Adjustment.objects.values_list("reason", "status")) == {
        ("DAMAGE", "PENDING"), ("INTERNAL_USE", "APPROVED"), ("PHYSICAL_COUNT", "APPROVED"),
    }
    count = PhysicalCount.objects.get()
    assert (count.status, count.category.name) == ("APPROVED", "Pinturas")
    assert count.lines.get(product__sku="PIN-ESM-N").difference == Decimal("-1.000")
    assert not count.lines.exclude(product__sku="PIN-ESM-N").exclude(difference=0).exists()
    transfer = Transfer.objects.get()
    assert (transfer.origin.code, transfer.destination.code) == ("PRAL", "VIT")
    assert transfer.lines.get(product__sku="BOM-LED-9").base_quantity == 10  # una caja de 10
    pending = Product.objects.get(sku="MAN-12")
    assert (pending.is_active, pending.price_pending) == (False, True)


def test_the_kardex_matches_and_nothing_is_below_the_minimum_or_zero():
    for level in StockLevel.objects.select_related("product", "warehouse"):
        total = StockMovement.objects.filter(product=level.product, warehouse=level.warehouse).aggregate(q=Sum("quantity"))["q"]
        assert total == level.quantity, (level.product.sku, level.warehouse.code)
        assert level.quantity >= 0
    assert inventory_report()["totals"]["negative"] == 0
    # La entrada del día 7 a otro precio movió el promedio del martillo.
    assert StockLevel.objects.get(product__sku="MAR-16", warehouse__code="PRAL").average_cost not in (Decimal(19000), Decimal(21000))


def test_void_and_return_are_dated_with_their_sale():
    voided = Sale.objects.get(status="VOIDED")
    day = timezone.localtime(voided.occurred_at).date()
    assert timezone.localtime(voided.voided_at).date() == day
    movements = StockMovement.objects.filter(reference=f"Anulación {voided.number}")
    assert movements.count() == voided.lines.count()
    assert {timezone.localtime(m.occurred_at).date() for m in movements} == {day}
    sale_return = SaleReturn.objects.get()
    day = timezone.localtime(sale_return.sale.occurred_at).date()
    assert timezone.localtime(sale_return.created_at).date() == day
    movement = StockMovement.objects.get(reference=f"Devolución {sale_return.number} de {sale_return.sale.number}")
    assert timezone.localtime(movement.occurred_at).date() == day
