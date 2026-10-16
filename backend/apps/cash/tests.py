import uuid
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.cash.models import Payment, Shift
from apps.cash.services import close_shift, open_shift, shift_summary
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
    record_movement(kind=StockMovement.Kind.RECEIPT, product=hammer, warehouse=warehouse, quantity=20, user=cashier)


def sell(cashier, shift, hammer, qty, payments):
    sale, _ = create_sale(
        user=cashier, shift=shift, client_uuid=uuid.uuid4(),
        lines=[{"product": hammer, "quantity": qty}], payments=payments,
    )
    return sale


# --- turnos -----------------------------------------------------------------

def test_only_one_open_shift_per_register(register, cashier, shift):
    with pytest.raises(ValidationError):
        open_shift(register=register, user=cashier, opening_float=D("50000"))


def test_register_can_reopen_after_closing(register, cashier, shift):
    close_shift(shift=shift, user=cashier, counted_cash=D("100000"))
    assert open_shift(register=register, user=cashier, opening_float=D("80000")).status == Shift.Status.OPEN


def test_closing_twice_is_rejected(cashier, shift):
    close_shift(shift=shift, user=cashier, counted_cash=D("100000"))
    with pytest.raises(ValidationError):
        close_shift(shift=shift, user=cashier, counted_cash=D("100000"))


# --- pagos ------------------------------------------------------------------

def test_cash_payment_computes_change(cashier, shift, hammer, stocked):
    sale = sell(cashier, shift, hammer, 1, [{"method": "CASH", "amount": D("50000")}])
    pay = sale.payments.get()
    assert (pay.amount, pay.received, pay.change) == (D("28000"), D("50000"), D("22000"))


def test_mixed_payment_card_plus_cash(cashier, shift, hammer, stocked):
    sale = sell(cashier, shift, hammer, 3, [  # total 84.000
        {"method": "CARD", "amount": D("60000"), "reference": "VOUCHER-881"},
        {"method": "CASH", "amount": D("30000")},
    ])
    card = sale.payments.get(method=Payment.Method.CARD)
    cash = sale.payments.get(method=Payment.Method.CASH)
    assert card.amount == D("60000") and card.reference == "VOUCHER-881"
    assert (cash.amount, cash.change) == (D("24000"), D("6000"))


@pytest.mark.parametrize("payments", [
    [{"method": "CASH", "amount": D("20000")}],                                    # falta dinero
    [{"method": "CARD", "amount": D("30000")}],                                    # tarjeta da de más
    [{"method": "TRANSFER", "amount": D("10000")}],                                # transferencia corta
    [{"method": "CARD", "amount": D("28000")}, {"method": "CASH", "amount": D("1000")}],  # efectivo sobrante
    [{"method": "CASH", "amount": D("0")}, {"method": "CARD", "amount": D("28000")}],     # pago en cero
    [],
])
def test_invalid_payments_are_rejected(cashier, shift, hammer, stocked, payments):
    with pytest.raises(ValidationError):
        sell(cashier, shift, hammer, 1, payments)
    assert not Payment.objects.exists()


# --- arqueo -----------------------------------------------------------------

def test_close_with_exact_cash_has_no_difference(cashier, shift, hammer, stocked):
    sell(cashier, shift, hammer, 1, [{"method": "CASH", "amount": D("30000")}])        # efectivo 28.000
    sell(cashier, shift, hammer, 2, [{"method": "TRANSFER", "amount": D("56000")}])    # transferencia
    sell(cashier, shift, hammer, 1, [
        {"method": "CARD", "amount": D("20000")}, {"method": "CASH", "amount": D("8000")},
    ])
    summary = shift_summary(shift)
    assert summary["sales"] == 3
    assert summary["by_method"] == {"CASH": D("36000"), "CARD": D("20000"), "TRANSFER": D("56000")}
    closed = close_shift(shift=shift, user=cashier, counted_cash=D("136000"), notes="Sin novedad")
    assert closed.expected_cash == D("136000")  # base 100.000 + efectivo 36.000
    assert closed.difference == 0


def test_close_records_shortage(cashier, shift, hammer, stocked):
    sell(cashier, shift, hammer, 1, [{"method": "CASH", "amount": D("28000")}])
    closed = close_shift(shift=shift, user=cashier, counted_cash=D("125000"))
    assert closed.difference == D("-3000")


def test_voided_sales_do_not_count(cashier, shift, hammer, stocked):
    sale = sell(cashier, shift, hammer, 1, [{"method": "CASH", "amount": D("28000")}])
    sale.status = "VOIDED"  # la anulación completa llega con la T6
    sale.save()
    assert shift_summary(shift)["expected_cash"] == D("100000")


# --- API --------------------------------------------------------------------

def api(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def test_open_sell_and_close_through_api(register, cashier, hammer, stocked):
    client = api(cashier)
    res = client.post("/api/cash/shifts/", {"register": register.pk, "opening_float": "50000"}, format="json")
    assert res.status_code == 201, res.data
    shift_id = res.data["id"]
    assert client.post(
        "/api/cash/shifts/", {"register": register.pk, "opening_float": "1"}, format="json"
    ).status_code == 400

    sale = {
        "client_uuid": str(uuid.uuid4()), "shift": shift_id,
        "lines": [{"product": hammer.pk, "quantity": "1"}],
        "payments": [{"method": "CASH", "amount": "28000"}],
    }
    assert client.post("/api/sales/", sale, format="json").status_code == 201

    summary = client.get(f"/api/cash/shifts/{shift_id}/").data["summary"]
    assert summary["expected_cash"] == "78000.00"

    res = client.post(f"/api/cash/shifts/{shift_id}/close/", {"counted_cash": "78000"}, format="json")
    assert res.status_code == 200
    assert res.data["status"] == "CLOSED"
    assert res.data["difference"] == "0.00"


def test_warehouse_staff_cannot_open_shift(register, make_user):
    res = api(make_user("aux", "Auxiliar de bodega")).post(
        "/api/cash/shifts/", {"register": register.pk, "opening_float": "0"}, format="json"
    )
    assert res.status_code == 403


def test_registers_list_shows_open_shift(register, cashier, shift, make_user):
    res = api(cashier).get("/api/cash/registers/")
    assert res.status_code == 200
    assert res.data == [{"id": register.pk, "code": "CAJA1", "name": "Caja 1", "warehouse": "PRAL", "open_shift": shift.pk}]
    close_shift(shift=shift, user=cashier, counted_cash=D("100000"))
    assert api(cashier).get("/api/cash/registers/").data[0]["open_shift"] is None
    assert api(make_user("aux", "Auxiliar de bodega")).get("/api/cash/registers/").status_code == 403
