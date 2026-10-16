"""Spec 003, T1: buscar y listar ventas, y el detalle con devoluciones."""
import datetime
import uuid
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.cash.models import CashRegister
from apps.cash.services import close_shift, open_shift
from apps.inventory.models import StockMovement
from apps.inventory.services import record_movement
from apps.sales.models import Sale
from apps.sales.returns import create_return, void_sale
from apps.sales.services import create_sale

pytestmark = pytest.mark.django_db
D = Decimal


def api(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.fixture
def cashier(make_user):
    return make_user("laura", "Caja")


@pytest.fixture
def supervisor(make_user):
    return make_user("sofia", "Supervisor")


@pytest.fixture
def stocked(cashier, warehouse, hammer):
    record_movement(kind=StockMovement.Kind.RECEIPT, product=hammer, warehouse=warehouse, quantity=50, user=cashier)


def sell(cashier, shift, hammer, qty=1, **extra):
    sale, _ = create_sale(
        user=cashier, shift=shift, client_uuid=uuid.uuid4(), lines=[{"product": hammer, "quantity": qty}],
        payments=[{"method": "CASH", "amount": D("28000") * qty}], **extra,
    )
    return sale


# --- listar -------------------------------------------------------------------

def test_lists_todays_sales_newest_first(supervisor, cashier, shift, hammer, stocked):
    first, second = sell(cashier, shift, hammer), sell(cashier, shift, hammer, 2)
    yesterday = sell(cashier, shift, hammer)
    Sale.objects.filter(pk=yesterday.pk).update(occurred_at=timezone.now() - datetime.timedelta(days=1))

    res = api(supervisor).get("/api/sales/")
    assert res.status_code == 200
    assert [s["number"] for s in res.data] == [second.number, first.number]
    row = res.data[0]
    assert (row["register"], row["seller"], row["salesperson"], row["total"]) == ("CAJA1", "laura", "laura", "56000.00")


@pytest.mark.parametrize("text", ["V-000{pk}", "v{pk}", "{pk}", " V-{pk} "])
def test_search_by_number_in_any_date(supervisor, cashier, shift, hammer, stocked, text):
    old = sell(cashier, shift, hammer)
    Sale.objects.filter(pk=old.pk).update(occurred_at=timezone.now() - datetime.timedelta(days=30))
    sell(cashier, shift, hammer)
    res = api(supervisor).get("/api/sales/", {"number": text.format(pk=old.pk)})
    assert [s["id"] for s in res.data] == [old.pk]


def test_bad_number_or_date_returns_400(supervisor):
    assert api(supervisor).get("/api/sales/", {"number": "factura 12"}).status_code == 400
    assert api(supervisor).get("/api/sales/", {"date": "16/10/2026"}).status_code == 400


def test_filter_by_date(supervisor, cashier, shift, hammer, stocked):
    old = sell(cashier, shift, hammer)
    when = timezone.now() - datetime.timedelta(days=3)
    Sale.objects.filter(pk=old.pk).update(occurred_at=when)
    sell(cashier, shift, hammer)
    day = timezone.localdate(when).isoformat()
    assert [s["id"] for s in api(supervisor).get("/api/sales/", {"date": day}).data] == [old.pk]


def test_filter_by_register_status_and_review(supervisor, cashier, shift, warehouse, hammer, stocked):
    other_register = CashRegister.objects.create(code="CAJA2", name="Caja 2", warehouse=warehouse)
    other_shift = open_shift(register=other_register, user=cashier, opening_float=D("0"))
    in_caja1, in_caja2 = sell(cashier, shift, hammer), sell(cashier, other_shift, hammer)
    voided = sell(cashier, shift, hammer)
    void_sale(sale=voided, user=supervisor, reason="Error")
    flagged = sell(cashier, shift, hammer)
    Sale.objects.filter(pk=flagged.pk).update(needs_review=True)

    client = api(supervisor)
    ids = lambda **q: {s["id"] for s in client.get("/api/sales/", q).data}  # noqa: E731
    assert ids(register=other_register.pk) == {in_caja2.pk}
    assert ids(status="VOIDED") == {voided.pk}
    assert ids(needs_review="1") == {flagged.pk}
    assert in_caja1.pk in ids()


def test_only_supervisors_and_reports_can_list(make_user, cashier):
    assert api(cashier).get("/api/sales/").status_code == 403
    assert api(make_user("andres", "Ventas")).get("/api/sales/").status_code == 403
    assert api(make_user("marta", "Jefe de bodega")).get("/api/sales/").status_code == 200  # reports.view


def test_cashier_still_creates_sales_on_same_url(cashier, shift, hammer, stocked):
    body = {
        "client_uuid": str(uuid.uuid4()), "shift": shift.pk,
        "lines": [{"product": hammer.pk, "quantity": "1"}], "payments": [{"method": "CASH", "amount": "28000"}],
    }
    assert api(cashier).post("/api/sales/", body, format="json").status_code == 201


# --- detalle ------------------------------------------------------------------

def test_detail_includes_returns_and_returned_quantity(supervisor, cashier, shift, hammer, stocked):
    sale = sell(cashier, shift, hammer, 3)
    line = sale.lines.get()
    create_return(
        sale=sale, user=supervisor, shift=shift, refund_method="CASH", reason="No le sirvió",
        client_uuid=uuid.uuid4(), lines=[{"sale_line": line, "quantity": 1}],
    )
    res = api(supervisor).get(f"/api/sales/{sale.pk}/")
    assert res.status_code == 200
    assert res.data["lines"][0]["returned_quantity"] == "1.000"
    assert res.data["lines"][0]["name"] == "Martillo 16 oz"
    assert [(r["total"], r["reason"], r["refund_method"]) for r in res.data["returns"]] == [("28000.00", "No le sirvió", "CASH")]
    assert res.data["register"] == "CAJA1"
    assert res.data["shift_open"] is True


def test_detail_says_when_shift_is_closed(supervisor, cashier, shift, hammer, stocked):
    sale = sell(cashier, shift, hammer)
    close_shift(shift=shift, user=cashier, counted_cash=D("128000"))
    assert api(supervisor).get(f"/api/sales/{sale.pk}/").data["shift_open"] is False


def test_detail_permissions(make_user, supervisor, cashier, shift, hammer, stocked):
    sale = sell(cashier, shift, hammer)
    assert api(supervisor).get(f"/api/sales/{sale.pk}/").status_code == 200
    assert api(make_user("marta", "Jefe de bodega")).get(f"/api/sales/{sale.pk}/").status_code == 200
    assert api(make_user("pedro", "Auxiliar de bodega")).get(f"/api/sales/{sale.pk}/").status_code == 403
