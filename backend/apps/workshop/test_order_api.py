"""API de órdenes de trabajo (spec 011, T4)."""
import uuid
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.invoicing.models import Business
from apps.sales.models import Order
from apps.sales.services import create_sale

from . import work_orders as svc
from .models import WorkOrder
from .services import register_motorcycle
from .test_work_orders import clerk, labor, main, mechanic, moto, oil, order, other, pads  # noqa: F401

pytestmark = pytest.mark.django_db
URL = "/api/workshop/orders/"
Status = WorkOrder.Status


@pytest.fixture(autouse=True)
def workshop_on(db):
    business = Business.load()
    business.workshop_enabled = True
    business.save()
    return business


def client(user):
    api = APIClient()
    api.force_authenticate(user)
    return api


@pytest.fixture
def desk(clerk):
    return client(clerk)


@pytest.fixture
def bench(mechanic):
    return client(mechanic)


def post(api, path, data=None):
    return api.post(f"{URL}{path}", data or {}, format="json")


# --- permisos y módulo -------------------------------------------------------------

def test_with_the_module_off_nothing_exists(desk, order, workshop_on):
    workshop_on.workshop_enabled = False
    workshop_on.save()
    for response in (desk.get(URL), desk.get(f"{URL}{order.pk}/"), post(desk, f"{order.pk}/diagnose/", {"diagnosis": "x"}),
                     desk.get(f"{URL}mechanics/")):
        assert response.status_code == 404


@pytest.mark.parametrize("role", ["Caja", "Ventas", "Jefe de bodega"])
def test_other_roles_cannot_use_it(make_user, order, role):
    api = client(make_user("otro", role))
    assert api.get(URL).status_code == 403
    assert api.get(f"{URL}{order.pk}/").status_code == 403
    assert post(api, f"{order.pk}/cancel/", {"reason": "x"}).status_code == 403


def test_a_mechanic_only_sees_their_orders(order, other, mechanic, bench):
    stranger = client(other)
    assert [row["number"] for row in bench.get(URL).data] == [order.number]
    assert stranger.get(URL).data == []
    assert stranger.get(f"{URL}{order.pk}/").status_code == 404
    assert post(stranger, f"{order.pk}/diagnose/", {"diagnosis": "x"}).status_code == 404
    assert post(stranger, f"{order.pk}/lines/", {}).status_code == 404


def test_a_mechanic_cannot_do_what_reception_does(bench, order, moto, mechanic):
    response = post(bench, "", {"motorcycle": moto.pk, "mileage": 1, "request": "x"})
    assert (response.status_code, response.data["detail"]) == (403, "Esto lo hace recepción del taller.")
    assert post(bench, f"{order.pk}/cancel/", {"reason": "x"}).status_code == 403
    assert post(bench, f"{order.pk}/assign/", {"mechanic": mechanic.pk}).status_code == 403


def test_mechanics_to_assign(desk, mechanic, other, clerk):
    other.is_active = False
    other.save()
    assert desk.get(f"{URL}mechanics/").data == [{"id": mechanic.pk, "username": "carlos", "name": "carlos"}]


# --- recibir y listar --------------------------------------------------------------

def test_receiving_a_motorcycle(desk, moto, mechanic):
    response = post(desk, "", {"motorcycle": moto.pk, "mileage": 15400, "request": "Cambio de aceite",
                               "condition": "Deja el casco", "mechanic": mechanic.pk})
    assert response.status_code == 201
    data = response.data
    assert (data["status"], data["mileage_in"], data["request"], data["condition"], data["received_by"]) == (
        Status.RECEIVED, 15400, "Cambio de aceite", "Deja el casco", "diana")
    assert data["number"] == f"OT-{data['id']:06d}"
    assert data["mechanic"] == {"id": mechanic.pk, "username": "carlos", "name": "carlos"}
    assert data["motorcycle"]["plate"] == "XYZ12A" and data["customer"]["name"] == "Jorge Ramírez"
    assert (data["lines"], data["till_order"], data["sale"], data["charged_total"]) == ([], None, None, "0.00")
    assert [e["status"] for e in data["events"]] == [Status.RECEIVED]
    again = post(desk, "", {"motorcycle": moto.pk, "mileage": 15400, "request": "Otra"})
    assert (again.status_code, again.data) == (400, ["La moto ya tiene una orden de trabajo abierta."])


def test_receiving_rules_answer_by_field(desk, moto):
    response = post(desk, "", {"motorcycle": moto.pk, "mileage": 15400, "request": "  "})
    assert (response.status_code, list(response.data)) == (400, ["request"])
    missing = post(desk, "", {"motorcycle": moto.pk, "request": "x"})
    assert (missing.status_code, missing.data) == (400, {"mileage": ["Este campo es requerido."]})


def test_the_list_by_status_mechanic_and_motorcycle(desk, order, clerk, mechanic, moto):
    second = register_motorcycle(user=clerk, owner=moto.owner, plate="ABC12D", brand="Honda")
    done = svc.receive_order(user=clerk, motorcycle=second, mileage=100, request="Lavado")
    svc.cancel(order=done, user=clerk, reason="No volvió")
    numbers = lambda q="": [row["number"] for row in desk.get(f"{URL}{q}").data]  # noqa: E731
    assert numbers() == [order.number]
    assert numbers("?status=CANCELLED") == [done.number]
    assert numbers("?status=ALL") == [done.number, order.number]
    assert numbers(f"?status=ALL&mechanic={mechanic.pk}") == [order.number]
    assert numbers(f"?status=ALL&motorcycle={second.pk}") == [done.number]
    assert numbers("?status=ALL&motorcycle=x") == []
    assert desk.get(f"{URL}?status=NADA").status_code == 400


def test_the_motorcycle_shows_its_orders(desk, order, moto):
    data = desk.get(f"/api/workshop/motorcycles/{moto.pk}/").data
    assert [(o["number"], o["status"], o["mileage_in"]) for o in data["work_orders"]] == [(order.number, Status.RECEIVED, 15400)]


# --- de punta a punta --------------------------------------------------------------

def test_the_whole_order_through_the_api(desk, bench, order, oil, labor, make_user, shift):
    assert post(bench, f"{order.pk}/diagnose/", {"diagnosis": "Aceite vencido"}).data["diagnosis"] == "Aceite vencido"
    assert post(bench, f"{order.pk}/lines/", {"product": oil.pk, "quantity": "1"}).status_code == 201
    data = post(bench, f"{order.pk}/lines/", {"product": labor.pk, "quantity": "1"}).data
    oil_line, work = data["lines"]
    assert (oil_line["sku"], oil_line["unit_price"], oil_line["approved"], oil_line["taken"]) == ("ACE-20W50", "32000.00", False, False)
    assert data["pending_total"] == "32000.00"
    price = {"unit_price": "25000"}
    denied = bench.patch(f"{URL}{order.pk}/lines/{work['id']}/", price, format="json")
    assert (denied.status_code, denied.data["detail"]) == (403, "Esto lo hace recepción del taller.")
    assert desk.patch(f"{URL}{order.pk}/lines/{work['id']}/", price, format="json").data["pending_total"] == "57000.00"
    assert post(bench, f"{order.pk}/send-for-approval/").data["status"] == Status.AWAITING_APPROVAL
    data = post(desk, f"{order.pk}/approve/", {"approved_by": "Jorge", "channel": "PHONE"}).data
    assert (data["status"], data["charged_total"], data["pending_total"]) == (Status.IN_REPAIR, "57000.00", "0.00")
    assert data["approvals"][0]["approved_by"] == "Jorge" and data["approvals"][0]["total"] == "57000.00"
    assert post(bench, f"{order.pk}/lines/{oil_line['id']}/take/").data["lines"][0]["taken"] is True
    assert post(bench, f"{order.pk}/ready/").data["status"] == Status.READY
    data = post(desk, f"{order.pk}/send-to-till/").data
    till = Order.objects.get(pk=data["till_order"]["id"])
    assert (data["till_order"]["code"], data["till_order"]["total"]) == (till.code, "57000.00")
    refused = post(desk, f"{order.pk}/deliver/")
    assert (refused.status_code, refused.data) == (400, [f"La orden {order.number} no está cobrada: mándala a la caja."])
    sale, _ = create_sale(user=make_user("laura", "Caja"), shift=shift, order=till, lines=None,
                          payments=[{"method": "CASH", "amount": Decimal("57000")}], client_uuid=uuid.uuid4())
    data = desk.get(f"{URL}{order.pk}/").data
    assert (data["sale"], data["till_order"]) == ({"id": sale.pk, "number": sale.number, "total": "57000.00"}, None)
    data = post(desk, f"{order.pk}/deliver/", {"mileage": 15420}).data
    assert (data["status"], data["mileage_out"]) == (Status.DELIVERED, 15420)
    assert [e["status"] for e in data["events"]][-1] == Status.DELIVERED


def test_lines_are_removed_and_returned(desk, bench, order, oil, pads):
    first = post(bench, f"{order.pk}/lines/", {"product": oil.pk, "quantity": "1"}).data["lines"][0]
    data = post(bench, f"{order.pk}/lines/", {"product": pads.pk, "quantity": "1"}).data
    assert len(bench.delete(f"{URL}{order.pk}/lines/{data['lines'][1]['id']}/").data["lines"]) == 1
    post(bench, f"{order.pk}/send-for-approval/")
    post(desk, f"{order.pk}/approve/", {"approved_by": "Jorge", "channel": "IN_PERSON"})
    post(bench, f"{order.pk}/lines/{first['id']}/take/")
    data = post(bench, f"{order.pk}/lines/{first['id']}/return/").data
    assert (data["lines"][0]["returned"], data["charged_total"]) == (True, "0.00")


def test_rule_errors_are_400_and_unknown_things_404(desk, bench, order, oil, clerk, moto):
    line = post(bench, f"{order.pk}/lines/", {"product": oil.pk, "quantity": "1"}).data["lines"][0]
    taken = post(bench, f"{order.pk}/lines/{line['id']}/take/")
    assert (taken.status_code, taken.data) == (400, [f"La orden {order.number} está recibida: no se puede sacar repuestos."])
    approve = post(desk, f"{order.pk}/approve/", {"approved_by": " ", "channel": "PHONE"})
    assert (approve.status_code, list(approve.data)) == (400, ["approved_by"])
    assert post(desk, f"{order.pk}/approve/", {"approved_by": "Jorge", "channel": "EMAIL"}).status_code == 400
    assert post(desk, f"{order.pk}/fly/").status_code == 404
    assert post(desk, f"{order.pk}/lines/{line['id']}/fly/").status_code == 404
    second = register_motorcycle(user=clerk, owner=moto.owner, plate="ABC12D", brand="Honda")
    elsewhere = svc.receive_order(user=clerk, motorcycle=second, mileage=100, request="Lavado")
    assert post(desk, f"{elsewhere.pk}/lines/{line['id']}/take/").status_code == 404  # la línea es de otra orden
    assert desk.delete(f"{URL}{elsewhere.pk}/lines/{line['id']}/").status_code == 404


def test_assign_and_cancel(desk, order, other):
    data = post(desk, f"{order.pk}/assign/", {"mechanic": other.pk}).data
    assert data["mechanic"]["username"] == "pablo"
    assert post(desk, f"{order.pk}/assign/", {"mechanic": None}).data["mechanic"] is None
    assert post(desk, f"{order.pk}/cancel/", {"reason": ""}).status_code == 400
    data = post(desk, f"{order.pk}/cancel/", {"reason": "No volvió"}).data
    assert (data["status"], data["events"][-1]["note"]) == (Status.CANCELLED, "No volvió")
