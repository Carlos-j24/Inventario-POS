"""API de mantenimientos e historial de la moto (spec 012, T3)."""
from datetime import timedelta

import pytest
from django.utils import timezone

from . import work_orders as svc
from .models import MaintenancePlan, MaintenanceReminder
from .test_maintenance import deliver, history, oil_plan, remind  # noqa: F401
from .test_order_api import client, desk, workshop_on  # noqa: F401
from .test_work_order_billing import CASH, cashier, charge, paid, ready  # noqa: F401
from .test_work_orders import approved, clerk, labor, main, mechanic, moto, oil, order, pads  # noqa: F401

pytestmark = pytest.mark.django_db
PLANS, DUE = "/api/workshop/plans/", "/api/workshop/maintenance/"
Status = MaintenanceReminder.Status


@pytest.fixture
def boss(make_user):
    return client(make_user("marta", "Jefe de bodega"))


def post(api, path, data=None):
    return api.post(path, data or {}, format="json")


# --- planes -----------------------------------------------------------------------------

def test_the_catalog_creates_and_changes_plans(boss, oil, labor):
    response = post(boss, PLANS, {"name": " Cambio de aceite ", "every_km": 3000, "every_days": 90, "products": [oil.pk]})
    assert response.status_code == 201
    plan = response.data
    assert (plan["name"], plan["every_km"], plan["every_days"], plan["is_active"]) == ("Cambio de aceite", 3000, 90, True)
    assert plan["product_list"] == [{"id": oil.pk, "sku": "ACE-20W50", "name": "Aceite 20W50"}]
    changed = boss.patch(f"{PLANS}{plan['id']}/", {"every_days": None, "products": [oil.pk, labor.pk], "is_active": False}, format="json")
    assert (changed.status_code, changed.data["every_days"], changed.data["is_active"]) == (200, None, False)
    assert [p["sku"] for p in changed.data["product_list"]] == ["ACE-20W50", "MO-TALLER"]
    post(boss, PLANS, {"name": "Revisión de frenos", "every_days": 180, "products": [oil.pk]})
    assert [p["name"] for p in boss.get(PLANS).data] == ["Revisión de frenos", "Cambio de aceite"]  # activos primero
    assert boss.get(f"{PLANS}{plan['id']}/").data["name"] == "Cambio de aceite"
    assert boss.delete(f"{PLANS}{plan['id']}/").status_code == 405  # se desactiva, no se borra


@pytest.mark.parametrize("data, field", [
    ({"name": "Nada", "products": "oil"}, "non_field_errors"),
    ({"name": "Cero", "every_km": 0, "products": "oil"}, "every_km"),
    ({"name": "Cero", "every_days": 0, "products": "oil"}, "every_days"),
    ({"name": "  ", "every_days": 30, "products": "oil"}, "name"),
    ({"name": "Sin productos", "every_days": 30, "products": []}, "products"),
    ({"name": "Cambio de aceite", "every_days": 30, "products": "oil"}, "name"),
])
def test_what_a_plan_needs(boss, oil, oil_plan, data, field):
    data = {**data, "products": [oil.pk] if data["products"] == "oil" else data["products"]}
    response = post(boss, PLANS, data)
    assert (response.status_code, list(response.data)) == (400, [field])


def test_removing_the_interval_left_in_a_patch_is_refused(boss, oil_plan):
    response = boss.patch(f"{PLANS}{oil_plan.pk}/", {"every_km": None, "every_days": None}, format="json")
    assert (response.status_code, response.data) == (400, {"non_field_errors": ["Di cada cuántos km, cada cuántos días o las dos cosas."]})
    assert boss.patch(f"{PLANS}{oil_plan.pk}/", {"every_km": None}, format="json").status_code == 200  # quedan los días


def test_reception_sees_plans_but_does_not_change_them(desk, oil_plan, oil):
    assert [p["name"] for p in desk.get(PLANS).data] == ["Cambio de aceite"]
    assert post(desk, PLANS, {"name": "Otro", "every_days": 30, "products": [oil.pk]}).status_code == 403
    assert desk.patch(f"{PLANS}{oil_plan.pk}/", {"is_active": False}, format="json").status_code == 403


@pytest.mark.parametrize("role", ["Mecánico", "Caja"])
def test_others_do_not_see_plans_nor_the_list(make_user, oil_plan, role):
    api = client(make_user("otro", role))
    assert api.get(PLANS).status_code == 403
    assert api.get(DUE).status_code == 403


def test_with_the_module_off_nothing_exists(desk, boss, oil_plan, workshop_on):
    workshop_on.workshop_enabled = False
    workshop_on.save()
    assert boss.get(PLANS).status_code == 404
    assert desk.get(DUE).status_code == 404
    assert post(desk, f"{DUE}1/notify/", {"channel": "PHONE"}).status_code == 404


# --- lista y acciones ---------------------------------------------------------------------

@pytest.fixture
def due(moto, order, oil_plan, clerk):
    history(moto, clerk, [(40, 13000), (0, 15000)])
    return remind(moto, oil_plan, order, due_date=timezone.localdate() + timedelta(days=60), due_mileage=15100)


def test_the_list_with_the_phone_and_why_it_is_due(desk, due, moto):
    [item] = desk.get(DUE).data
    assert item["id"] == due.pk
    assert item["motorcycle"]["plate"] == "XYZ12A" and item["motorcycle"]["mileage"] == 15000
    assert item["owner"] == {"id": moto.owner_id, "name": "Jorge Ramírez", "phone": "3001234567"}
    assert (item["plan"]["name"], item["status"], item["due_mileage"]) == ("Cambio de aceite", Status.PENDING, 15100)
    assert (item["due_on"], item["by_km"], item["estimated"], item["daily_km"]) == (timezone.localdate() + timedelta(days=2), True, True, "50.0")
    assert (item["source_order"], item["done_order"], item["notices"]) == (f"OT-{due.source_order_id:06d}", None, [])


def test_notify_adjust_and_dismiss(desk, due, clerk):
    data = post(desk, f"{DUE}{due.pk}/notify/", {"channel": "WHATSAPP"}).data
    assert data["status"] == Status.NOTIFIED and [n["channel"] for n in data["notices"]] == ["WHATSAPP"]
    assert desk.get(DUE).data == []  # avisado: solo con ?notified=1
    assert [r["id"] for r in desk.get(f"{DUE}?notified=1").data] == [due.pk]
    december = timezone.localdate() + timedelta(days=40)
    response = post(desk, f"{DUE}{due.pk}/adjust/", {"due_date": december.isoformat(), "note": "Viene en diciembre"})
    assert response.json()["due_date"] == december.isoformat()  # en la respuesta, como texto
    data = response.data
    assert (data["due_date"], data["due_mileage"], data["note"]) == (december, None, "Viene en diciembre")
    assert desk.get(f"{DUE}?notified=1").data == []  # ya no vence esta semana
    data = post(desk, f"{DUE}{due.pk}/dismiss/", {"note": "Vendió la moto"}).data
    assert (data["status"], data["note"], data["closed_at"] is not None) == (Status.DISMISSED, "Vendió la moto", True)
    assert data["due_on"] is None  # cerrado: no vence


def test_action_errors(desk, due):
    assert post(desk, f"{DUE}{due.pk}/notify/", {"channel": "EMAIL"}).status_code == 400
    response = post(desk, f"{DUE}{due.pk}/adjust/", {"note": "x"})
    assert (response.status_code, response.data) == (400, ["Pon una fecha, un kilometraje o los dos."])
    response = post(desk, f"{DUE}{due.pk}/dismiss/", {"note": ""})
    assert (response.status_code, response.data) == (400, {"note": ["Escribe por qué se descarta."]})
    assert post(desk, f"{DUE}{due.pk}/fly/").status_code == 404
    assert post(desk, f"{DUE}999/notify/", {"channel": "PHONE"}).status_code == 404


def test_the_list_by_plan(desk, due, moto, order, oil):
    other = MaintenancePlan.objects.create(name="Revisión de frenos", every_days=30)
    other_due = remind(moto, other, order, due_date=timezone.localdate())
    assert [r["id"] for r in desk.get(f"{DUE}?plan={other.pk}").data] == [other_due.pk]
    assert [r["id"] for r in desk.get(DUE).data] == [other_due.pk, due.pk]  # hoy primero, luego en 2 días
    assert desk.get(f"{DUE}?plan=999").data == [] and desk.get(f"{DUE}?plan=x").data == []


# --- historial en la ficha de la moto -------------------------------------------------------

def test_the_motorcycle_history_and_its_reminders(desk, paid, ready, clerk, moto, oil_plan, mechanic, oil, labor):
    deliver(ready, clerk, mileage=15420)
    visit = svc.receive_order(user=clerk, motorcycle=moto, mileage=15500, request="Ruido en la cadena", mechanic=mechanic)
    svc.add_line(order=visit, user=mechanic, product=oil, quantity=1)
    svc.approve(order=visit, user=clerk, approved_by="Jorge", channel="PHONE")  # aprobada pero abierta: todavía no es historia
    data = desk.get(f"/api/workshop/motorcycles/{moto.pk}/").data
    open_, done = data["history"]
    assert (open_["status"], open_["lines"], open_["total"], open_["delivered_at"]) == ("IN_REPAIR", [], None, None)
    assert (done["number"], done["status"], done["mileage_in"], done["mileage_out"]) == (ready.number, "DELIVERED", 15400, 15420)
    assert done["delivered_at"] is not None and done["mechanic"] == "carlos" and done["total"] == "57000.00"
    assert [(line["sku"], line["is_service"], line["total"]) for line in done["lines"]] == [
        ("ACE-20W50", False, "32000.00"), ("MO-TALLER", True, "25000.00")]
    [reminder] = data["reminders"]
    assert (reminder["plan"]["name"], reminder["status"], reminder["due_mileage"], reminder["source_order"]) == (
        "Cambio de aceite", Status.PENDING, 18420, ready.number)
    assert reminder["due_on"] == timezone.localdate() + timedelta(days=90)


def test_the_history_leaves_out_what_was_returned_and_open_reminders_go_first(
        desk, order, clerk, mechanic, oil, labor, pads, cashier, shift, moto, oil_plan):
    approved(order, clerk, mechanic, oil, labor)
    svc.add_line(order=order, user=mechanic, product=pads, quantity=1)
    svc.approve(order=order, user=clerk, approved_by="Jorge", channel="PHONE")
    for line in order.lines.filter(is_service=False):
        svc.take_part(line=line, user=mechanic)
    svc.return_part(line=order.lines.get(product=pads), user=mechanic)
    svc.mark_ready(order=order, user=mechanic)
    charge(cashier, shift, svc.send_to_till(order=order, user=clerk))
    deliver(order, clerk)
    closed = remind(moto, MaintenancePlan.objects.create(name="Viejo", every_days=10), order, due_date=timezone.localdate(),
                    status=Status.DONE, done_order=order, closed_at=timezone.now())
    data = desk.get(f"/api/workshop/motorcycles/{moto.pk}/").data
    assert [line["sku"] for line in data["history"][0]["lines"]] == ["ACE-20W50", "MO-TALLER"]  # sin las pastillas regresadas
    assert [(r["plan"]["name"], r["due_on"] is None) for r in data["reminders"]] == [("Cambio de aceite", False), ("Viejo", True)]
    assert (data["reminders"][1]["id"], data["reminders"][1]["done_order"]) == (closed.pk, order.number)
