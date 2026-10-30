"""Lo que deja sembrado `seed_demo --taller` (spec 009, T4). Se siembra una vez para todo el módulo."""
from collections import Counter
from datetime import timedelta
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
from apps.reports.costs import inventory_report, margins_report
from apps.sales.models import Order, Quote, Sale, SaleLine
from apps.workshop.maintenance import due_of, due_reminders
from apps.workshop.models import MaintenancePlan, MaintenanceReminder, Motorcycle, WorkOrder

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
    assert set(seeded) == {u for u, *_ in USERS} | {"diana.recepcion", "jhon.mecanico"}


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
    assert Order.objects.get(status="PENDING", work_order=None).lines.filter(product__sku="LLA-90-18").exists()
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
    # la última, de hoy: la recibieron en el taller (spec 011)
    assert [(r.mileage, days_ago(r.recorded_at)) for r in readings] == [(12500, 120), (14100, 35), (15200, 3), (15400, 0)]
    assert (boxer.mileage, days_ago(boxer.mileage_at), days_ago(boxer.created_at)) == (15400, 0, 120)
    reset = Motorcycle.objects.get(plate="GHI78H").mileage_readings.order_by("-recorded_at")[1]
    assert (reset.mileage, reset.previous, reset.note) == (120, 31200, "Cambio de tablero")


def test_the_car_wash_services_have_no_stock():
    washes = Product.objects.filter(is_service=True, category__name="Lavadero")
    assert {(p.sku, p.category.name, p.sale_price) for p in washes} == {
        ("LAV-150", "Lavadero", Decimal("12000")), ("LAV-AC", "Lavadero", Decimal("18000")), ("LAV-MOT", "Lavadero", Decimal("15000")),
    }
    assert not StockLevel.objects.filter(product__in=washes).exists()
    assert not StockMovement.objects.filter(product__in=washes).exists()


def test_washes_every_worked_day_some_with_a_part():
    lines = SaleLine.objects.filter(product__category__name="Lavadero", sale__status="COMPLETED").select_related("sale")
    per_day = Counter(timezone.localtime(line.sale.occurred_at).date() for line in lines)
    history = {day: n for day, n in per_day.items() if day != timezone.localdate()}
    assert len(history) >= 10 and all(2 <= n <= 4 for n in history.values()), per_day
    assert all(line.movement is None for line in lines)
    assert all(line.sale.created_at == line.sale.occurred_at for line in lines)  # la lista de Ventas los pone en su día
    with_grease = Sale.objects.filter(lines__is_service=True).filter(lines__product__sku="GRA-CAD").distinct()
    assert with_grease.count() >= 5  # el primero del día lleva grasa mientras alcance el stock


def test_today_a_wash_with_oil_and_an_offline_wash_without_review():
    today = timezone.localdate()
    with_oil = Sale.objects.filter(lines__product__sku="LAV-150", occurred_at__date=today).filter(lines__product__sku="ACE-20W50").get()
    assert (with_oil.offline, with_oil.needs_review, with_oil.total) == (False, False, Decimal("44000.00"))
    offline = Sale.objects.get(offline=True, lines__product__sku="LAV-AC", occurred_at__date=today)
    assert (offline.needs_review, offline.total) == (False, Decimal("18000.00"))


def test_the_margins_report_shows_the_washes_apart():
    report = margins_report(timezone.localdate() - timedelta(days=30), timezone.localdate())
    services = [r for r in report["rows"] if r["is_service"]]
    assert {r["sku"] for r in services} == {"LAV-150", "LAV-AC", "LAV-MOT", "MO-TALLER"}  # la mano de obra de la orden cobrada
    assert all(r["cost"] == "0.00" for r in services)
    assert Decimal(report["totals"]["services_net_sales"]) == sum(Decimal(r["net_sales"]) for r in services) > 0


def test_one_motorcycle_changed_owner():
    honda = Motorcycle.objects.get(plate="DEF56G")
    current, previous = honda.ownerships.select_related("customer")
    assert (current.customer.name, current.ended_at) == ("Mensajería Express del Caquetá S.A.S.", None)
    assert previous.customer.name == "Luis Gómez"
    assert (days_ago(previous.started_at), days_ago(previous.ended_at), days_ago(current.started_at)) == (400, 30, 30)
    assert honda.owner == current.customer


# --- órdenes de trabajo (spec 011, T7) ----------------------------------------------

def orders():
    """La orden de hoy de cada moto (las visitas de meses atrás son de la spec 012)."""
    rows = WorkOrder.objects.select_related("motorcycle", "mechanic").order_by("received_at", "pk")
    return {o.motorcycle.plate or o.motorcycle.vin: o for o in rows}


def test_a_mechanic_and_an_order_in_every_status():
    jhon = User.objects.get(username="jhon.mecanico")
    assert [r.name for r in jhon.roles.all()] == ["Mecánico"]
    labor = Product.objects.get(sku="MO-TALLER")
    assert (labor.is_service, labor.category.name) == (True, "Taller")
    assert {plate: o.status for plate, o in orders().items()} == {
        "DEF56G": "DELIVERED", "JKL90B": "CANCELLED", "GHI78H": "READY", "XYZ12A": "IN_REPAIR",
        "ABC34D": "AWAITING_APPROVAL", "9F2NKD125T0001234": "RECEIVED",
    }
    assert [o.mechanic for o in orders().values() if o.status == "RECEIVED"] == [None]
    assert all(o.mechanic == jhon for o in orders().values() if o.status != "RECEIVED")
    assert days_ago(orders()["DEF56G"].received_at) == 2


def test_the_boxer_of_the_spec_has_a_change_without_approval():
    boxer = orders()["XYZ12A"]
    assert (boxer.mileage_in, boxer.request, boxer.condition) == (15400, "Cambio de aceite y revisar frenos", "Rayón en el tanque, deja el casco")
    lines = {line.product.sku: line for line in boxer.lines.select_related("product")}
    assert {sku: (line.approved, line.movement_id is not None) for sku, line in lines.items()} == {
        "ACE-20W50": (True, True), "PAS-DEL": (True, True), "MO-TALLER": (True, False), "BAN-TRA": (False, False),
    }
    assert lines["MO-TALLER"].unit_price == Decimal("25000")
    assert boxer.approvals.get().approved_by == "Jorge Ramírez"
    out = StockMovement.objects.get(product__sku="PAS-DEL", kind="WORKSHOP_OUT", reference=f"Orden {boxer.number}")
    assert (out.warehouse.code, out.quantity) == ("PRAL", Decimal("-1"))


def test_delivered_after_the_till_charged_it_and_one_waiting_in_the_till():
    honda = orders()["DEF56G"]
    sale = Sale.objects.get(order__work_order=honda)
    assert (sale.status, sale.total, honda.mileage_out) == ("COMPLETED", Decimal("69000.00"), 21052)
    assert all(line.movement.kind == "WORKSHOP_OUT" for line in sale.lines.filter(is_service=False))  # no se descontó otra vez
    assert not sale.needs_review
    waiting = Order.objects.get(status="PENDING", work_order=orders()["GHI78H"])
    assert waiting.total == Decimal("39000.00")


def test_the_cancelled_one_returned_its_part():
    suzuki = orders()["JKL90B"]
    line = suzuki.lines.get(product__sku="BUJ-C7")
    assert (line.movement.kind, line.returned_movement.kind) == ("WORKSHOP_OUT", "WORKSHOP_RETURN")
    assert suzuki.events.last().note == "El cliente se la llevó sin arreglar"


# --- historial y recordatorios (spec 012, T6) ---------------------------------------

def reminder(plate, plan, **filters):
    return MaintenanceReminder.objects.select_related("source_order", "done_order").get(
        motorcycle__plate=plate, plan__name=plan, **filters,
    )


def test_example_maintenance_plans():
    plans = {p.name: (p.every_km, p.every_days, sorted(p.products.values_list("sku", flat=True)), p.is_active)
             for p in MaintenancePlan.objects.all()}
    assert plans == {
        "Cambio de aceite": (3000, 90, ["ACE-10W40", "ACE-20W50"], True),
        "Revisión de frenos": (5000, 180, ["BAN-TRA", "PAS-DEL"], True),
        "Kit de arrastre": (15000, None, ["CAD-428", "KIT-BOX100"], True),
    }


def test_past_visits_are_delivered_orders_in_the_history():
    past = WorkOrder.objects.filter(status="DELIVERED").exclude(pk=orders()["DEF56G"].pk).select_related("motorcycle")
    assert {(o.motorcycle.plate, o.mileage_in, o.mileage_out, days_ago(o.received_at)) for o in past} == {
        ("XYZ12A", 12500, 12500, 120), ("JKL90B", 48500, 48500, 100), ("ABC34D", 5600, 5600, 55), ("DEF56G", 20400, 20400, 90),
    }
    for order in past:
        assert {e.status for e in order.events.all()} >= {"RECEIVED", "DELIVERED"}
        assert all(days_ago(e.at) == days_ago(order.received_at) for e in order.events.all())
        assert Sale.objects.get(order__work_order=order).status == "COMPLETED"
        assert all(days_ago(r.created_at) == days_ago(order.received_at) for r in order.reminders_created.all())
    assert days_ago(Motorcycle.objects.get(plate="ABC34D").created_at) == 55


def test_a_reminder_in_every_state():
    today = timezone.localdate()
    late = reminder("JKL90B", "Cambio de aceite")  # vencido por fecha
    due = due_of(late)
    assert (late.status, late.due_date, late.due_mileage) == ("PENDING", today - timedelta(days=10), 51500)
    assert (due.on, due.by_km) == (today - timedelta(days=10), False)

    by_km = reminder("ABC34D", "Cambio de aceite")  # vence por km estimados (unos 50 km al día)
    due = due_of(by_km)
    assert (by_km.status, by_km.due_date, by_km.due_mileage) == ("PENDING", today + timedelta(days=35), 8600)
    assert (due.on, due.by_km, due.estimated, due.usage) == (today + timedelta(days=5), True, True, Decimal(50))

    notified = reminder("XYZ12A", "Cambio de aceite")
    notice = notified.notices.get()
    assert (notified.status, notice.channel, notice.user.username, days_ago(notice.at)) == (
        "NOTIFIED", "WHATSAPP", "diana.recepcion", 28)
    assert notified.due_date == today - timedelta(days=30)

    done = reminder("DEF56G", "Cambio de aceite", status="DONE")
    honda = orders()["DEF56G"]
    assert (done.source_order.mileage_in, done.done_order) == (20400, honda)
    following = reminder("DEF56G", "Cambio de aceite", status="PENDING")
    assert (following.source_order, following.due_mileage, following.due_date) == (honda, 24052, today + timedelta(days=90))

    dismissed = reminder("DEF56G", "Kit de arrastre")
    assert (dismissed.status, dismissed.note, days_ago(dismissed.closed_at)) == (
        "DISMISSED", "La mensajería le cambia el kit con su propio mecánico", 25)
    assert dismissed.due_mileage == 35400 and dismissed.due_date is None

    assert MaintenanceReminder.objects.count() == 6
    assert [(r.motorcycle.plate, r.status) for r, _ in due_reminders(include_notified=True)] == [
        ("XYZ12A", "NOTIFIED"), ("JKL90B", "PENDING"), ("ABC34D", "PENDING"),
    ]
