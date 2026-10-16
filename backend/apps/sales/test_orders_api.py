"""Spec 002, T4: API de pedidos y cobro por /api/sales/."""
import datetime
import uuid
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.inventory.models import StockLevel, StockMovement
from apps.inventory.services import record_movement
from apps.sales.models import Order, Sale, business_date

pytestmark = pytest.mark.django_db
D = Decimal


def api(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.fixture
def vendor(make_user):
    return make_user("andres", "Ventas")


@pytest.fixture
def cashier(make_user):
    return make_user("laura", "Caja")


@pytest.fixture
def stocked(cashier, warehouse, cable, hammer):
    for product, qty in ((cable, 300), (hammer, 10)):
        record_movement(kind=StockMovement.Kind.RECEIPT, product=product, warehouse=warehouse, quantity=qty, user=cashier)


def new_order(client, *lines, key=None):
    return client.post("/api/orders/", {
        "client_uuid": str(key or uuid.uuid4()),
        "lines": [{"product": p.pk, "quantity": str(q), **({"unit": u} if u else {})} for p, q, u in lines],
    }, format="json")


def charge(client, shift, order_id, order_lines=None, amount="1000000", key=None):
    body = {
        "client_uuid": str(key or uuid.uuid4()), "shift": shift.pk, "order": order_id,
        "payments": [{"method": "CASH", "amount": amount}],
    }
    if order_lines is not None:
        body["order_lines"] = order_lines
    return client.post("/api/sales/", body, format="json")


# --- crear y listar -----------------------------------------------------------

def test_vendor_creates_order_and_gets_code_and_warnings(vendor, cable, hammer, stocked):
    res = new_order(api(vendor), (cable, "12.5", None), (hammer, 20, None))
    assert res.status_code == 201, res.data
    assert 1000 <= res.data["code"] <= 9999
    assert res.data["status"] == "PENDING"
    assert res.data["salesperson"] == "andres"
    assert res.data["total"] == "600000.00"  # 40.000 + 20 × 28.000
    assert [(l["sku"], l["unit"], l["unit_price"]) for l in res.data["lines"]] == [
        ("CAB-12", "m", "3200.00"), ("MAR-16", "und", "28000.00"),
    ]
    assert res.data["warnings"] == [{"sku": "MAR-16", "name": "Martillo 16 oz", "kind": "sin_existencias", "available": "10.000"}]


def test_retry_returns_same_order(vendor, hammer, stocked):
    client, key = api(vendor), uuid.uuid4()
    first = new_order(client, (hammer, 1, None), key=key)
    again = new_order(client, (hammer, 1, None), key=key)
    assert (first.status_code, again.status_code) == (201, 200)
    assert first.data["id"] == again.data["id"]


def test_invalid_order_returns_400(vendor, hammer):
    assert new_order(api(vendor), (hammer, "0.5", None)).status_code == 400
    assert api(vendor).post("/api/orders/", {"client_uuid": str(uuid.uuid4()), "lines": []}, format="json").status_code == 400


def test_warehouse_staff_cannot_create_orders(make_user, hammer):
    assert new_order(api(make_user("pedro", "Auxiliar de bodega")), (hammer, 1, None)).status_code == 403


def test_vendor_lists_only_own_pending_orders_of_today(make_user, vendor, cashier, hammer, stocked):
    other = make_user("otra", "Ventas")
    mine = new_order(api(vendor), (hammer, 1, None)).data
    new_order(api(other), (hammer, 1, None))
    old = new_order(api(vendor), (hammer, 1, None)).data
    Order.objects.filter(pk=old["id"]).update(business_date=business_date() - datetime.timedelta(days=1))

    assert [o["id"] for o in api(vendor).get("/api/orders/").data] == [mine["id"]]
    # La caja ve los pendientes de todos (para el cliente que no recuerda el código).
    assert len(api(cashier).get("/api/orders/").data) == 2
    assert len(api(cashier).get("/api/orders/?mine=1").data) == 0


# --- buscar por código ----------------------------------------------------------

def test_cashier_finds_todays_order_by_code(vendor, cashier, hammer, stocked):
    order = new_order(api(vendor), (hammer, 2, None)).data
    res = api(cashier).get(f"/api/orders/code/{order['code']}/")
    assert res.status_code == 200
    assert res.data["id"] == order["id"]
    assert res.data["lines"][0]["quantity"] == "2.000"


def test_code_from_yesterday_is_not_found_and_vendor_cannot_search(vendor, cashier, hammer, stocked):
    order = new_order(api(vendor), (hammer, 1, None)).data
    Order.objects.filter(pk=order["id"]).update(business_date=business_date() - datetime.timedelta(days=1))
    assert api(cashier).get(f"/api/orders/code/{order['code']}/").status_code == 404
    assert api(vendor).get(f"/api/orders/code/{order['code']}/").status_code == 403


# --- cancelar -----------------------------------------------------------------

def test_cancel_own_order_but_not_others(make_user, vendor, hammer, stocked):
    order = new_order(api(vendor), (hammer, 1, None)).data
    assert api(make_user("otra", "Ventas")).post(f"/api/orders/{order['id']}/cancel/").status_code == 403
    res = api(vendor).post(f"/api/orders/{order['id']}/cancel/")
    assert res.status_code == 200
    assert res.data["status"] == "CANCELLED"
    assert api(vendor).post(f"/api/orders/{order['id']}/cancel/").status_code == 400


# --- cobrar -------------------------------------------------------------------

def test_cashier_charges_order_through_sales_endpoint(vendor, cashier, shift, hammer, stocked):
    order = new_order(api(vendor), (hammer, 2, None)).data
    res = charge(api(cashier), shift, order["id"], amount="60000")
    assert res.status_code == 201, res.data
    assert res.data["salesperson"] == "andres"
    assert res.data["seller"] == "laura"
    assert res.data["order_code"] == order["code"]
    assert res.data["total"] == "56000.00"
    assert res.data["payments"][0]["change"] == "4000.00"
    assert api(cashier).get(f"/api/orders/code/{order['code']}/").data["status"] == "PAID"
    assert api(cashier).get(f"/api/orders/code/{order['code']}/").data["sale_number"] == res.data["number"]


def test_cashier_charges_part_of_the_order(vendor, cashier, shift, cable, hammer, stocked):
    order = new_order(api(vendor), (cable, "12.5", None), (hammer, 2, None)).data
    hammer_line = next(l for l in order["lines"] if l["sku"] == "MAR-16")
    res = charge(api(cashier), shift, order["id"], order_lines=[{"order_line": hammer_line["id"], "quantity": "1"}])
    assert res.status_code == 201, res.data
    assert res.data["total"] == "28000.00"
    assert StockLevel.objects.get(product=cable).quantity == 300


def test_charging_twice_returns_400(vendor, cashier, shift, hammer, stocked):
    order = new_order(api(vendor), (hammer, 1, None)).data
    assert charge(api(cashier), shift, order["id"]).status_code == 201
    res = charge(api(cashier), shift, order["id"])
    assert res.status_code == 400
    assert "ya fue cobrado" in str(res.data)
    assert Sale.objects.count() == 1


def test_vendor_cannot_charge_own_order(vendor, shift, hammer, stocked):
    order = new_order(api(vendor), (hammer, 1, None)).data
    assert charge(api(vendor), shift, order["id"]).status_code == 403


@pytest.mark.parametrize("extra", [
    {"lines": [{"product": 1, "quantity": "1"}]},   # pedido y líneas sueltas a la vez
    {"offline": True},                               # los pedidos se cobran con conexión
])
def test_bad_order_charge_requests_return_400(vendor, cashier, shift, hammer, stocked, extra):
    order = new_order(api(vendor), (hammer, 1, None)).data
    body = {
        "client_uuid": str(uuid.uuid4()), "shift": shift.pk, "order": order["id"],
        "payments": [{"method": "CASH", "amount": "100000"}], **extra,
    }
    assert api(cashier).post("/api/sales/", body, format="json").status_code == 400
    assert not Sale.objects.exists()


def test_sale_without_lines_or_order_returns_400(cashier, shift):
    body = {"client_uuid": str(uuid.uuid4()), "shift": shift.pk, "payments": [{"method": "CASH", "amount": "1"}]}
    assert api(cashier).post("/api/sales/", body, format="json").status_code == 400


def test_direct_sale_still_works_and_shows_cashier_as_salesperson(cashier, shift, hammer, stocked):
    body = {
        "client_uuid": str(uuid.uuid4()), "shift": shift.pk,
        "lines": [{"product": hammer.pk, "quantity": "1"}],
        "payments": [{"method": "CASH", "amount": "28000"}],
    }
    res = api(cashier).post("/api/sales/", body, format="json")
    assert res.status_code == 201, res.data
    assert (res.data["salesperson"], res.data["seller"], res.data["order_code"]) == ("laura", "laura", None)


def test_serializer_shows_yesterdays_pending_order_as_expired(vendor, hammer, stocked):
    # Ningún endpoint devuelve hoy pedidos viejos, pero los reportes lo harán: deben salir vencidos.
    from apps.sales.serializers import OrderSerializer

    order = new_order(api(vendor), (hammer, 1, None)).data
    Order.objects.filter(pk=order["id"]).update(business_date=business_date() - datetime.timedelta(days=1))
    assert OrderSerializer(Order.objects.get(pk=order["id"])).data["status"] == "EXPIRED"
