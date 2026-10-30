"""Mantenimientos, los servicios (spec 012, T2)."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from apps.sales.returns import void_sale

from . import maintenance as mt
from . import work_orders as svc
from .models import MaintenancePlan, MaintenanceReminder, MileageReading, Motorcycle
from .test_work_order_billing import CASH, cashier, charge, paid, ready  # noqa: F401
from .test_work_orders import approved, clerk, labor, main, mechanic, moto, oil, order, pads  # noqa: F401

pytestmark = pytest.mark.django_db
Status = MaintenanceReminder.Status
D = Decimal
DAY = date(2026, 10, 30)


@pytest.fixture
def oil_plan(oil):
    plan = MaintenancePlan.objects.create(name="Cambio de aceite", every_km=3000, every_days=90)
    plan.products.add(oil)
    return plan


def deliver(order, clerk, mileage=None):
    return svc.deliver(order=order, user=clerk, mileage=mileage)


def reminders(moto):
    return [(r.plan.name, r.status, r.due_date, r.due_mileage) for r in moto.reminders.order_by("id")]


# --- estimación ------------------------------------------------------------------------

def test_daily_usage_from_the_readings():
    readings = [(DAY - timedelta(days=20), 14000, None), (DAY - timedelta(days=5), 14500, 14000), (DAY, 15000, 14500)]
    assert mt.daily_usage(readings, DAY) == 50
    assert mt.daily_usage(readings[1:], DAY) is None  # menos de 14 días entre la primera y la última
    assert mt.daily_usage(readings[:1], DAY) is None
    assert mt.daily_usage([], DAY) is None
    assert mt.daily_usage([(DAY - timedelta(days=30), 15000, None), (DAY, 15000, 15000)], DAY) is None  # no se mueve


def test_only_the_last_twelve_months_count():
    readings = [(DAY - timedelta(days=400), 0, None), (DAY - timedelta(days=365), 9000, 0), (DAY, 12650, 9000)]
    assert mt.daily_usage(readings, DAY) == 10  # la de hace 400 días no cuenta; la de hace 365 sí


def test_a_new_dashboard_starts_the_count_again():
    readings = [
        (DAY - timedelta(days=60), 30000, None), (DAY - timedelta(days=30), 31200, 30000),
        (DAY - timedelta(days=20), 100, 31200),  # cambio de tablero
        (DAY, 1100, 100),
    ]
    assert mt.daily_usage(readings, DAY) == 50
    assert mt.daily_usage(readings[:3] + [(DAY - timedelta(days=10), 600, 100)], DAY) is None  # 10 días desde el tablero nuevo


def test_when_the_motorcycle_reaches_the_km():
    assert mt.km_due_date(16000, DAY, 15000, D(50)) == DAY + timedelta(days=20)
    assert mt.km_due_date(16001, DAY, 15000, D(50)) == DAY + timedelta(days=21)  # se redondea hacia arriba
    assert mt.km_due_date(15000, DAY, 15000, D(50)) == DAY  # ya llegó: vence el día de la lectura
    assert mt.km_due_date(14000, DAY, 15000, None) == DAY
    assert mt.km_due_date(16000, DAY, 15000, None) is None  # sin uso no se estima
    assert mt.km_due_date(None, DAY, 15000, D(50)) is None


# --- al entregar ------------------------------------------------------------------------

def test_delivering_creates_the_next_maintenance(paid, ready, clerk, moto, oil_plan, labor):
    MaintenancePlan.objects.create(name="Kit de arrastre", every_km=15000).products.add(labor)  # la mano de obra también cumple
    other = MaintenancePlan.objects.create(name="Revisión de frenos", every_days=180)
    deliver(ready, clerk, mileage=15420)
    today = timezone.localdate()
    assert reminders(moto) == [
        ("Cambio de aceite", Status.PENDING, today + timedelta(days=90), 18420),
        ("Kit de arrastre", Status.PENDING, None, 30420),
    ]
    assert {r.source_order for r in moto.reminders.all()} == {ready}
    assert not other.reminders.exists()  # la orden no llevaba nada de ese plan


def test_a_plan_by_days_only(paid, ready, clerk, moto, oil):
    plan = MaintenancePlan.objects.create(name="Revisión general", every_days=180)
    plan.products.add(oil)
    deliver(ready, clerk)
    assert reminders(moto) == [("Revisión general", Status.PENDING, timezone.localdate() + timedelta(days=180), None)]


def test_a_returned_part_does_not_count(order, clerk, mechanic, oil, labor, pads, cashier, shift, moto):
    plan = MaintenancePlan.objects.create(name="Revisión de frenos", every_days=180)
    plan.products.add(pads)
    approved(order, clerk, mechanic, oil, labor)
    svc.add_line(order=order, user=mechanic, product=pads, quantity=1)
    svc.approve(order=order, user=clerk, approved_by="Jorge", channel="PHONE")
    for line in order.lines.filter(is_service=False):
        svc.take_part(line=line, user=mechanic)
    svc.return_part(line=order.lines.get(product=pads), user=mechanic)
    svc.mark_ready(order=order, user=mechanic)
    charge(cashier, shift, svc.send_to_till(order=order, user=clerk))
    deliver(order, clerk)
    assert reminders(moto) == []


def next_visit(moto, clerk, mechanic, oil, labor, cashier, shift, mileage):
    order = svc.receive_order(user=clerk, motorcycle=moto, mileage=mileage, request="Cambio de aceite", mechanic=mechanic)
    approved(order, clerk, mechanic, oil, labor)
    svc.take_part(line=order.lines.get(product=oil), user=mechanic)
    svc.mark_ready(order=order, user=mechanic)
    charge(cashier, shift, svc.send_to_till(order=order, user=clerk))
    return deliver(order, clerk)


def test_the_next_delivery_closes_the_previous_reminder(paid, ready, clerk, mechanic, moto, oil_plan, oil, labor, cashier, shift):
    deliver(ready, clerk)
    first = moto.reminders.get()
    later = next_visit(moto, clerk, mechanic, oil, labor, cashier, shift, 18300)
    first.refresh_from_db()
    assert (first.status, first.done_order, first.closed_by, first.closed_at is not None) == (Status.DONE, later, clerk, True)
    current = moto.reminders.get(status=Status.PENDING)
    assert (current.source_order, current.due_mileage) == (later, 21300)


def test_an_inactive_plan_closes_but_does_not_create(paid, ready, clerk, mechanic, moto, oil_plan, oil, labor, cashier, shift):
    deliver(ready, clerk)
    oil_plan.is_active = False
    oil_plan.save()
    next_visit(moto, clerk, mechanic, oil, labor, cashier, shift, 18300)
    assert [r[1] for r in reminders(moto)] == [Status.DONE]


def test_delivering_again_after_voiding_the_sale_recalculates_the_same(paid, ready, clerk, moto, oil_plan, cashier, shift):
    deliver(ready, clerk, mileage=15420)
    void_sale(sale=paid, user=cashier, reason="Medio de pago equivocado")  # vuelve a Lista (spec 011)
    charge(cashier, shift, svc.send_to_till(order=ready, user=clerk))
    deliver(ready, clerk, mileage=15500)
    assert reminders(moto) == [("Cambio de aceite", Status.PENDING, timezone.localdate() + timedelta(days=90), 18500)]


def test_delivering_again_with_an_inactive_plan_keeps_what_it_had(paid, ready, clerk, moto, oil_plan, cashier, shift):
    deliver(ready, clerk, mileage=15420)
    void_sale(sale=paid, user=cashier, reason="Medio de pago equivocado")
    oil_plan.is_active = False
    oil_plan.save()
    charge(cashier, shift, svc.send_to_till(order=ready, user=clerk))
    deliver(ready, clerk, mileage=15500)
    assert [(r[1], r[3]) for r in reminders(moto)] == [(Status.PENDING, 18420)]


# --- qué vence ------------------------------------------------------------------------

def history(moto, clerk, readings):
    """Lecturas de (días atrás, km); la última queda como el kilometraje de la moto."""
    MileageReading.objects.filter(motorcycle=moto).delete()
    previous = None
    now = timezone.now()
    for back, km in readings:
        MileageReading.objects.create(motorcycle=moto, mileage=km, previous=previous, recorded_at=now - timedelta(days=back), recorded_by=clerk)
        previous = km
    Motorcycle.objects.filter(pk=moto.pk).update(mileage=previous, mileage_at=now - timedelta(days=readings[-1][0]))
    moto.refresh_from_db()


def remind(moto, plan, order, **due):
    return MaintenanceReminder.objects.create(motorcycle=moto, plan=plan, source_order=order, **due)


@pytest.fixture
def plans(oil):
    return {name: MaintenancePlan.objects.create(name=name, every_days=30) for name in ("A", "B", "C", "D", "E")}


def test_what_is_due_overdue_first(moto, order, clerk, plans):
    today = timezone.localdate()
    history(moto, clerk, [(40, 13000), (0, 15000)])  # 50 km al día
    late = remind(moto, plans["A"], order, due_date=today - timedelta(days=3))
    week = remind(moto, plans["B"], order, due_date=today + timedelta(days=7))
    remind(moto, plans["C"], order, due_date=today + timedelta(days=8))  # todavía no
    by_km = remind(moto, plans["D"], order, due_date=today + timedelta(days=90), due_mileage=15100)  # en 2 días aprox.
    remind(moto, plans["E"], order, due_mileage=16000)  # en 20 días aprox.: todavía no
    due = mt.due_reminders(today=today)
    assert [r for r, _ in due] == [late, by_km, week]
    assert [(d.on, d.by_km, d.estimated) for _, d in due] == [
        (today - timedelta(days=3), False, False), (today + timedelta(days=2), True, True), (today + timedelta(days=7), False, False),
    ]
    assert due[1][1].usage == 50


def test_a_reading_past_the_km_makes_it_due_now(moto, order, clerk, plans):
    today = timezone.localdate()
    history(moto, clerk, [(2, 15000), (1, 15200)])  # sin uso estimable, pero ya pasó los km
    reached = remind(moto, plans["A"], order, due_date=today + timedelta(days=60), due_mileage=15100)
    unknown = remind(moto, plans["B"], order, due_mileage=16000)
    [(row, due)] = mt.due_reminders(today=today)
    assert row == reached
    assert (due.on, due.by_km, due.estimated, due.usage) == (today - timedelta(days=1), True, False, None)
    assert mt.due_of(unknown, today).on is None  # sin uso, solo cuando vuelva y se lea


def test_the_list_shows_notified_on_request_and_filters_by_plan(moto, order, clerk, plans):
    today = timezone.localdate()
    pending = remind(moto, plans["A"], order, due_date=today)
    told = remind(moto, plans["B"], order, due_date=today, status=Status.NOTIFIED)
    remind(moto, plans["C"], order, due_date=today, status=Status.DISMISSED, closed_at=timezone.now())
    remind(moto, plans["D"], order, due_date=today, status=Status.DONE, done_order=order, closed_at=timezone.now())
    assert [r for r, _ in mt.due_reminders(today=today)] == [pending]
    assert [r for r, _ in mt.due_reminders(today=today, include_notified=True)] == [pending, told]
    assert [r for r, _ in mt.due_reminders(today=today, include_notified=True, plan=plans["B"])] == [told]


# --- avisar, ajustar y descartar -------------------------------------------------------

@pytest.fixture
def reminder(moto, order, oil_plan):
    return remind(moto, oil_plan, order, due_date=timezone.localdate(), due_mileage=18400)


def test_reception_notifies_as_many_times_as_needed(reminder, clerk, mechanic):
    with pytest.raises(PermissionDenied, match="recepción"):
        mt.notify(reminder=reminder, user=mechanic, channel="WHATSAPP")
    with pytest.raises(ValidationError, match="WhatsApp o llamada"):
        mt.notify(reminder=reminder, user=clerk, channel="EMAIL")
    assert mt.notify(reminder=reminder, user=clerk, channel="WHATSAPP").status == Status.NOTIFIED
    mt.notify(reminder=reminder, user=clerk, channel="PHONE")
    assert [(n.channel, n.user) for n in reminder.notices.all()] == [("WHATSAPP", clerk), ("PHONE", clerk)]


def test_adjusting_needs_a_due_and_a_note(reminder, clerk, mechanic):
    december = date(2026, 12, 15)
    with pytest.raises(PermissionDenied):
        mt.adjust(reminder=reminder, user=mechanic, due_date=december, note="x")
    with pytest.raises(ValidationError, match="fecha, un kilometraje"):
        mt.adjust(reminder=reminder, user=clerk, note="Viene en diciembre")
    with pytest.raises(ValidationError, match="mayor que cero"):
        mt.adjust(reminder=reminder, user=clerk, due_mileage=0, note="Viene en diciembre")
    with pytest.raises(ValidationError, match="por qué se ajusta"):
        mt.adjust(reminder=reminder, user=clerk, due_date=december, note="  ")
    adjusted = mt.adjust(reminder=reminder, user=clerk, due_date=december, note=" El cliente dijo que viene en diciembre ")
    assert (adjusted.due_date, adjusted.due_mileage, adjusted.note, adjusted.status) == (
        december, None, "El cliente dijo que viene en diciembre", Status.PENDING)


def test_dismissing_closes_it_with_a_note(reminder, clerk, mechanic):
    with pytest.raises(PermissionDenied):
        mt.dismiss(reminder=reminder, user=mechanic, note="Vendió la moto")
    with pytest.raises(ValidationError, match="por qué se descarta"):
        mt.dismiss(reminder=reminder, user=clerk, note="")
    done = mt.dismiss(reminder=reminder, user=clerk, note=" Vendió la moto ")
    assert (done.status, done.note, done.closed_by, done.closed_at is not None) == (Status.DISMISSED, "Vendió la moto", clerk, True)
    for action, extra in ((mt.notify, {"channel": "PHONE"}), (mt.adjust, {"due_date": DAY, "note": "x"}), (mt.dismiss, {"note": "x"})):
        with pytest.raises(ValidationError, match="está descartado"):
            action(reminder=reminder, user=clerk, **extra)
