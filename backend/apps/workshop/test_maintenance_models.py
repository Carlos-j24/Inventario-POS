"""Mantenimientos, el modelo (spec 012, T1)."""
import datetime

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import Client
from django.utils import timezone

from apps.accounts.models import User

from .models import MaintenanceNotice, MaintenancePlan, MaintenanceReminder, WorkOrder
from .test_work_order_models import clerk, labor, moto, oil, receive  # noqa: F401

pytestmark = pytest.mark.django_db
Status = MaintenanceReminder.Status
DAY = datetime.date(2027, 1, 27)


@pytest.fixture
def plan(oil):
    plan = MaintenancePlan.objects.create(name="Cambio de aceite", every_km=3000, every_days=90)
    plan.products.add(oil)
    return plan


@pytest.fixture
def order(moto, clerk):
    return receive(moto, clerk)


def remind(moto, plan, order, **extra):
    return MaintenanceReminder.objects.create(motorcycle=moto, plan=plan, source_order=order, **{"due_date": DAY, **extra})


def broken(**fields):
    """Guarda sin pasar por las validaciones de Python: la base de datos también debe negarse."""
    with pytest.raises(IntegrityError), transaction.atomic():
        MaintenancePlan.objects.create(**fields)


# --- planes ----------------------------------------------------------------------------

def test_a_plan_by_km_by_days_or_both(oil, labor):
    both = MaintenancePlan.objects.create(name="Cambio de aceite", every_km=3000, every_days=90)
    both.products.add(oil, labor)
    assert [p.sku for p in both.products.order_by("sku")] == ["ACE-20W50", "MO-MANT"]
    assert list(oil.maintenance_plans.all()) == [both]
    MaintenancePlan.objects.create(name="Kit de arrastre", every_km=15000)
    MaintenancePlan.objects.create(name="Revisión de frenos", every_days=180)
    assert [str(p) for p in MaintenancePlan.objects.all()] == ["Cambio de aceite", "Kit de arrastre", "Revisión de frenos"]
    assert both.is_active is True


def test_a_plan_needs_an_interval_greater_than_zero():
    broken(name="Nada")
    broken(name="Cero km", every_km=0)
    broken(name="Cero días", every_km=3000, every_days=0)
    with pytest.raises(ValidationError) as error:
        MaintenancePlan(name="Nada").full_clean()
    assert "Di cada cuántos km, cada cuántos días o las dos cosas." in str(error.value)
    with pytest.raises(ValidationError, match="mayores que cero"):
        MaintenancePlan(name="Cero", every_days=0).full_clean()


def test_plan_names_do_not_repeat(plan):
    with pytest.raises(IntegrityError), transaction.atomic():
        MaintenancePlan.objects.create(name="Cambio de aceite", every_days=30)


# --- recordatorios ---------------------------------------------------------------------

def test_a_reminder_by_date_km_or_both(moto, plan, order):
    reminder = remind(moto, plan, order, due_mileage=18400)
    assert (reminder.status, reminder.done_order, reminder.note, reminder.closed_at) == (Status.PENDING, None, "", None)
    assert list(moto.reminders.all()) == [reminder] and list(order.reminders_created.all()) == [reminder]
    assert str(reminder) == "XYZ12A · Bajaj Boxer CT 100 · Cambio de aceite"
    reminder.status = Status.DISMISSED
    reminder.closed_at = timezone.now()
    reminder.save()
    assert remind(moto, plan, order, due_date=None, due_mileage=18400).pk  # solo por km
    with pytest.raises(IntegrityError), transaction.atomic():
        MaintenanceReminder.objects.create(motorcycle=moto, plan=plan, source_order=order)  # sin fecha ni km


def test_only_one_open_reminder_per_motorcycle_and_plan(moto, plan, order, clerk):
    first = remind(moto, plan, order)
    order.status = WorkOrder.Status.DELIVERED
    order.save()
    later = receive(moto, clerk)  # otra visita, aunque sea otra orden
    with pytest.raises(IntegrityError), transaction.atomic():
        remind(moto, plan, later, status=Status.NOTIFIED)
    first.status, first.done_order, first.closed_at = Status.DONE, order, timezone.now()
    first.save()
    second = remind(moto, plan, order)  # el siguiente, una vez hecho el anterior
    other = MaintenancePlan.objects.create(name="Revisión de frenos", every_days=180)
    assert remind(moto, other, order).pk  # otro plan, otro recordatorio abierto
    assert second.status == Status.PENDING


def test_done_needs_the_order_and_closing_needs_a_date(moto, plan, order):
    with pytest.raises(IntegrityError), transaction.atomic():
        remind(moto, plan, order, status=Status.DONE, closed_at=timezone.now())  # sin la orden que lo cumplió
    for status in (Status.DONE, Status.DISMISSED):
        with pytest.raises(IntegrityError), transaction.atomic():
            remind(moto, plan, order, status=status, done_order=order)  # sin fecha de cierre
    done = remind(moto, plan, order, status=Status.DONE, done_order=order, closed_at=timezone.now(), closed_by=order.received_by)
    assert list(order.reminders_done.all()) == [done]


def test_notices_in_order(moto, plan, order, clerk):
    reminder = remind(moto, plan, order)
    MaintenanceNotice.objects.create(reminder=reminder, channel="WHATSAPP", user=clerk)
    MaintenanceNotice.objects.create(reminder=reminder, channel="PHONE", user=clerk)
    assert [n.get_channel_display() for n in reminder.notices.all()] == ["WhatsApp", "Llamada"]
    assert str(reminder.notices.first()) == "XYZ12A · Bajaj Boxer CT 100 · Cambio de aceite · WhatsApp"


# --- admin ------------------------------------------------------------------------------

@pytest.fixture
def admin_client():
    client = Client()
    client.force_login(User.objects.create_superuser("jefe", password="clave-de-prueba-123"))
    return client


def test_the_admin_edits_plans_but_does_not_delete_them(admin_client, plan):
    assert admin_client.get("/admin/workshop/maintenanceplan/add/").status_code == 200
    page = admin_client.get(f"/admin/workshop/maintenanceplan/{plan.pk}/change/").content.decode()
    assert 'name="_save"' in page and "Cambio de aceite" in page
    assert admin_client.post(f"/admin/workshop/maintenanceplan/{plan.pk}/delete/").status_code == 403


def test_the_admin_only_shows_reminders(admin_client, moto, plan, order, clerk):
    reminder = remind(moto, plan, order, due_mileage=18400)
    MaintenanceNotice.objects.create(reminder=reminder, channel="WHATSAPP", user=clerk)
    listing = admin_client.get("/admin/workshop/maintenancereminder/").content.decode()
    assert "Cambio de aceite" in listing and "Pendiente" in listing
    page = admin_client.get(f"/admin/workshop/maintenancereminder/{reminder.pk}/change/")
    assert page.status_code == 200 and "WhatsApp" in page.content.decode()
    assert 'name="_save"' not in page.content.decode()
    assert admin_client.get("/admin/workshop/maintenancereminder/add/").status_code == 403
    assert admin_client.post(f"/admin/workshop/maintenancereminder/{reminder.pk}/delete/").status_code == 403
