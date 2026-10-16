import uuid
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.cash.models import Refund
from apps.cash.services import close_shift, open_shift, shift_summary
from apps.catalog.models import Unit
from apps.inventory.models import StockLevel, StockMovement
from apps.inventory.services import record_movement
from apps.sales.models import Sale, SaleReturn
from apps.sales.returns import create_return, void_sale
from apps.sales.services import create_sale

pytestmark = pytest.mark.django_db
D = Decimal


def stock(product, warehouse):
    return StockLevel.objects.get(product=product, warehouse=warehouse).quantity


@pytest.fixture
def cashier(make_user):
    return make_user("laura", "Caja")


@pytest.fixture
def supervisor(make_user):
    return make_user("sofia", "Supervisor")


@pytest.fixture
def stocked(cashier, warehouse, hammer, cable):
    for product, qty in ((hammer, 10), (cable, 300)):
        record_movement(kind=StockMovement.Kind.RECEIPT, product=product, warehouse=warehouse, quantity=qty, user=cashier)


@pytest.fixture
def sale(cashier, shift, hammer, cable, stocked):
    """3 martillos (84.000) + 1 rollo de cable (320.000) = 404.000 en efectivo."""
    sale, _ = create_sale(
        user=cashier, shift=shift, client_uuid=uuid.uuid4(),
        lines=[
            {"product": hammer, "quantity": 3},
            {"product": cable, "quantity": 1, "unit": Unit.objects.get(code="rollo")},
        ],
        payments=[{"method": "CASH", "amount": D("404000")}],
    )
    return sale


def line_of(sale, product):
    return sale.lines.get(product=product)


def give_back(sale, user, shift, items, method="CASH", key=None):
    return create_return(
        sale=sale, user=user, shift=shift, refund_method=method, reason="Cliente no lo necesitó",
        client_uuid=key or uuid.uuid4(),
        lines=[{"sale_line": line, "quantity": qty} for line, qty in items],
    )


# --- anular -----------------------------------------------------------------

def test_void_returns_all_stock_and_removes_cash(supervisor, shift, sale, warehouse, hammer, cable):
    void_sale(sale=sale, user=supervisor, reason="Error de digitación")
    sale.refresh_from_db()
    assert sale.status == Sale.Status.VOIDED
    assert sale.voided_by == supervisor
    assert stock(hammer, warehouse) == 10
    assert stock(cable, warehouse) == 300  # el rollo vuelve como 100 m
    assert shift_summary(shift)["expected_cash"] == D("100000")
    assert StockMovement.objects.filter(kind="RETURN", reference=f"Anulación {sale.number}").count() == 2


def test_void_twice_is_rejected(supervisor, sale):
    void_sale(sale=sale, user=supervisor, reason="Error")
    with pytest.raises(ValidationError):
        void_sale(sale=sale, user=supervisor, reason="Error")


def test_void_needs_reason(supervisor, sale):
    with pytest.raises(ValidationError):
        void_sale(sale=sale, user=supervisor, reason="  ")


def test_void_after_shift_closed_is_rejected(supervisor, cashier, shift, sale, warehouse, hammer):
    close_shift(shift=shift, user=cashier, counted_cash=D("504000"))
    with pytest.raises(ValidationError):
        void_sale(sale=sale, user=supervisor, reason="Error")
    assert stock(hammer, warehouse) == 7


def test_void_with_returns_is_rejected(supervisor, shift, sale, hammer):
    give_back(sale, supervisor, shift, [(line_of(sale, hammer), 1)])
    with pytest.raises(ValidationError):
        void_sale(sale=sale, user=supervisor, reason="Error")


# --- devolver ---------------------------------------------------------------

def test_partial_return_refunds_proportionally(supervisor, shift, sale, warehouse, hammer):
    ret, created = give_back(sale, supervisor, shift, [(line_of(sale, hammer), 1)])
    assert created
    assert ret.total == D("28000")
    assert ret.lines.get().subtotal + ret.lines.get().tax == D("28000")
    assert stock(hammer, warehouse) == 8
    assert shift_summary(shift)["expected_cash"] == D("100000") + D("404000") - D("28000")


def test_return_by_roll_restores_meters(supervisor, shift, sale, warehouse, cable):
    give_back(sale, supervisor, shift, [(line_of(sale, cable), 1)])
    assert stock(cable, warehouse) == 300


def test_cannot_return_more_than_sold(supervisor, shift, sale, warehouse, hammer):
    line = line_of(sale, hammer)
    give_back(sale, supervisor, shift, [(line, 2)])
    with pytest.raises(ValidationError):
        give_back(sale, supervisor, shift, [(line, 2)])
    assert stock(hammer, warehouse) == 9
    assert SaleReturn.objects.count() == 1


def test_returns_in_parts_add_up_to_the_line_total(supervisor, shift, cashier, cable, stocked):
    # 1 m a 3.199,99 devuelto en tres partes: redondeando cada parte sobraría un centavo
    # (1.065,60 + 1.065,60 + 1.068,80 = 3.200,00); la última reembolsa el resto exacto.
    sale, _ = create_sale(
        user=cashier, shift=shift, client_uuid=uuid.uuid4(), offline=True,
        lines=[{"product": cable, "quantity": D("1"), "unit_price": D("3199.99")}],
        payments=[{"method": "CASH", "amount": D("3199.99")}],
    )
    line = sale.lines.get()
    totals = [give_back(sale, supervisor, shift, [(line, D("0.333"))])[0].total for _ in range(2)]
    totals.append(give_back(sale, supervisor, shift, [(line, D("0.334"))])[0].total)
    assert sum(totals) == D("3199.99")


def test_return_from_other_sale_line_is_rejected(supervisor, shift, sale, cashier, hammer):
    other, _ = create_sale(
        user=cashier, shift=shift, client_uuid=uuid.uuid4(),
        lines=[{"product": hammer, "quantity": 1}], payments=[{"method": "CASH", "amount": D("28000")}],
    )
    with pytest.raises(ValidationError):
        give_back(sale, supervisor, shift, [(other.lines.get(), 1)])


def test_return_after_shift_closed_refunds_from_new_shift(supervisor, cashier, register, shift, sale, hammer):
    close_shift(shift=shift, user=cashier, counted_cash=D("504000"))
    new_shift = open_shift(register=register, user=cashier, opening_float=D("50000"))
    with pytest.raises(ValidationError):  # el turno viejo ya no puede devolver dinero
        give_back(sale, supervisor, shift, [(line_of(sale, hammer), 1)])
    give_back(sale, supervisor, new_shift, [(line_of(sale, hammer), 1)])
    assert shift_summary(new_shift)["expected_cash"] == D("22000")
    shift.refresh_from_db()
    assert shift.expected_cash == D("504000")  # el arqueo cerrado no cambia


def test_card_refund_does_not_touch_the_drawer(supervisor, shift, sale, hammer):
    give_back(sale, supervisor, shift, [(line_of(sale, hammer), 1)], method="CARD")
    summary = shift_summary(shift)
    assert summary["refunds"]["CARD"] == D("28000")
    assert summary["expected_cash"] == D("504000")


def test_same_client_uuid_returns_once(supervisor, shift, sale, warehouse, hammer):
    key = uuid.uuid4()
    give_back(sale, supervisor, shift, [(line_of(sale, hammer), 1)], key=key)
    _, created = give_back(sale, supervisor, shift, [(line_of(sale, hammer), 1)], key=key)
    assert not created
    assert stock(hammer, warehouse) == 8
    assert Refund.objects.count() == 1


# --- API --------------------------------------------------------------------

def api(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def test_cashier_cannot_void_or_return(cashier, shift, sale, hammer):
    client = api(cashier)
    assert client.post(f"/api/sales/{sale.pk}/void/", {"reason": "x"}, format="json").status_code == 403
    body = {
        "client_uuid": str(uuid.uuid4()), "shift": shift.pk, "refund_method": "CASH", "reason": "x",
        "lines": [{"line": line_of(sale, hammer).pk, "quantity": "1"}],
    }
    assert client.post(f"/api/sales/{sale.pk}/returns/", body, format="json").status_code == 403


def test_supervisor_voids_through_api(supervisor, sale):
    res = api(supervisor).post(f"/api/sales/{sale.pk}/void/", {"reason": "Error de caja"}, format="json")
    assert res.status_code == 200, res.data
    assert res.data["status"] == "VOIDED"
    again = api(supervisor).post(f"/api/sales/{sale.pk}/void/", {"reason": "Error de caja"}, format="json")
    assert again.status_code == 400


def test_supervisor_returns_through_api(supervisor, shift, sale, hammer):
    body = {
        "client_uuid": str(uuid.uuid4()), "shift": shift.pk, "refund_method": "CASH",
        "reason": "Producto defectuoso", "lines": [{"line": line_of(sale, hammer).pk, "quantity": "2"}],
    }
    client = api(supervisor)
    res = client.post(f"/api/sales/{sale.pk}/returns/", body, format="json")
    assert res.status_code == 201, res.data
    assert res.data["number"].startswith("D-")
    assert res.data["total"] == "56000.00"
    assert res.data["refund_method"] == "CASH"
    assert client.post(f"/api/sales/{sale.pk}/returns/", body, format="json").status_code == 200
