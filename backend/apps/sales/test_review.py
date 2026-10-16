import uuid
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.cash.services import close_shift
from apps.inventory.models import StockMovement
from apps.inventory.services import record_movement
from apps.sales.services import create_sale

pytestmark = pytest.mark.django_db
D = Decimal


@pytest.fixture
def cashier(make_user):
    return make_user("laura", "Caja")


@pytest.fixture
def stocked(cashier, warehouse, hammer):
    record_movement(kind=StockMovement.Kind.RECEIPT, product=hammer, warehouse=warehouse, quantity=5, user=cashier)


def sell(cashier, shift, hammer, qty, price=None, offline=False):
    line = {"product": hammer, "quantity": qty}
    if price is not None:
        line["unit_price"] = D(price)
    total = D(price or "28000") * qty
    sale, _ = create_sale(
        user=cashier, shift=shift, client_uuid=uuid.uuid4(), offline=offline,
        lines=[line], payments=[{"method": "CASH", "amount": total}],
    )
    return sale


def api(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def test_review_inbox_lists_flagged_sales_with_reasons(make_user, cashier, shift, hammer, stocked):
    sell(cashier, shift, hammer, 1)                                    # normal: no aparece
    cheap = sell(cashier, shift, hammer, 1, price="25000", offline=True)
    short = sell(cashier, shift, hammer, 6, price="28000", offline=True)  # quedan 3 → −3
    res = api(make_user("marta", "Jefe de bodega")).get("/api/sales/review/")
    assert res.status_code == 200
    assert [s["id"] for s in res.data] == [cheap.pk, short.pk]
    assert res.data[0]["reasons"] == ["Precio distinto al del catálogo"]
    assert res.data[1]["reasons"] == ["Dejó stock negativo"]


def test_late_offline_sale_says_shift_was_closed(make_user, cashier, shift, hammer, stocked):
    close_shift(shift=shift, user=cashier, counted_cash=D("100000"))
    sell(cashier, shift, hammer, 1, price="28000", offline=True)
    res = api(make_user("marta", "Jefe de bodega")).get("/api/sales/review/")
    assert res.data[0]["reasons"] == ["Llegó con el turno cerrado"]


def test_marking_reviewed_removes_it_from_inbox(make_user, cashier, shift, hammer, stocked):
    sale = sell(cashier, shift, hammer, 1, price="25000", offline=True)
    client = api(make_user("marta", "Jefe de bodega"))
    res = client.post(f"/api/sales/{sale.pk}/review/", {"note": "Precio de la semana pasada"}, format="json")
    assert res.status_code == 200, res.data
    sale.refresh_from_db()
    assert sale.needs_review  # la marca queda para la historia
    assert sale.review_note == "Precio de la semana pasada"
    assert client.get("/api/sales/review/").data == []
    assert client.post(f"/api/sales/{sale.pk}/review/", {}, format="json").status_code == 400


def test_normal_sale_cannot_be_reviewed(make_user, cashier, shift, hammer, stocked):
    sale = sell(cashier, shift, hammer, 1)
    res = api(make_user("marta", "Jefe de bodega")).post(f"/api/sales/{sale.pk}/review/", {}, format="json")
    assert res.status_code == 400


def test_cashier_cannot_see_review_inbox(cashier):
    assert api(cashier).get("/api/sales/review/").status_code == 403
