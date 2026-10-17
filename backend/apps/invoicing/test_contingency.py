"""Contingencia: ventas sin conexión con número de un bloque reservado (spec 005, T5)."""
import datetime
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework.test import APIClient

from apps.cash.models import CashRegister
from apps.sales.services import create_sale

from .models import ContingencyBlock, FiscalDocument, NumberingResolution
from .numbering import take_numbers
from .queue import alert, process_queue

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("stocked")]
Kind = FiscalDocument.Kind
OCCURRED = datetime.datetime(2026, 10, 17, 14, 30, tzinfo=datetime.timezone.utc)


@pytest.fixture(autouse=True)
def invoicing_on(settings):
    settings.INVOICING_ENABLED = True


def offline_sale(user, shift, product, number=None, **kwargs):
    sale, _ = create_sale(
        user=user, shift=shift, client_uuid=uuid.uuid4(), offline=True, occurred_at=OCCURRED,
        lines=[{"product": product, "quantity": Decimal("1"), "unit_price": Decimal("28000")}],
        payments=[{"method": "CASH", "amount": "28000"}], contingency_number=number, **kwargs,
    )
    return sale


def api(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def reserve(user, register):
    return api(user).post("/api/invoicing/contingency-blocks/", {"register": register.pk}, format="json")


# --- bloques -----------------------------------------------------------------

def test_the_pos_reserves_consecutive_blocks(cashier, register, contingency):
    first, second = reserve(cashier, register), reserve(cashier, register)
    assert (first.status_code, first.data) == (201, {"register": register.pk, "prefix": "CT1", "start": 1, "end": 50})
    assert (second.data["start"], second.data["end"]) == (51, 100)
    assert ContingencyBlock.objects.filter(register=register, reserved_by=cashier).count() == 2
    contingency.refresh_from_db()
    assert contingency.next_number == 101


def test_a_block_never_goes_past_the_range(cashier, register, contingency, settings):
    settings.CONTINGENCY_BLOCK_SIZE = 10
    NumberingResolution.objects.filter(pk=contingency.pk).update(next_number=995)
    res = reserve(cashier, register)
    assert (res.data["start"], res.data["end"]) == (995, 1000)
    res = reserve(cashier, register)
    assert res.status_code == 400
    assert "se agotó" in res.data["detail"]


def test_take_numbers_gives_what_is_left(register, contingency):
    assert take_numbers(register, "CONTINGENCY", 3)[1:] == (1, 3)
    NumberingResolution.objects.filter(pk=contingency.pk).update(next_number=999)
    assert take_numbers(register, "CONTINGENCY", 5)[1:] == (999, 1000)


def test_blocks_need_invoicing_numbering_and_cash_permission(cashier, register, make_user, settings):
    res = reserve(cashier, register)
    assert (res.status_code, "no tiene resolución" in res.data["detail"]) == (400, True)
    assert reserve(make_user("vende", "Ventas"), register).status_code == 403
    settings.INVOICING_ENABLED = False
    assert reserve(cashier, register).status_code == 409


def test_status_tells_the_pos_whether_invoicing_is_on(cashier, settings):
    assert api(cashier).get("/api/invoicing/status/").data == {"enabled": True}
    settings.INVOICING_ENABLED = False
    assert api(cashier).get("/api/invoicing/status/").data == {"enabled": False}


# --- ventas sin conexión ------------------------------------------------------

def test_offline_sale_keeps_the_number_printed_on_its_ticket(cashier, shift, register, hammer, contingency, numbering):
    reserve(cashier, register)
    doc = offline_sale(cashier, shift, hammer, number=7).fiscal_documents.get()
    assert (doc.kind, doc.contingency, doc.code, doc.resolution, doc.issued_at) == (Kind.POS, True, "CT17", contingency, OCCURRED)
    assert [e.kind for e in doc.events.all()] == ["created"]


@pytest.mark.parametrize("number, why", [(None, None), (500, "no es de un bloque")])
def test_without_a_valid_number_it_is_numbered_on_arrival(cashier, shift, register, hammer, contingency, numbering, number, why):
    reserve(cashier, register)  # 1–50
    doc = offline_sale(cashier, shift, hammer, number=number).fiscal_documents.get()
    assert (doc.code, doc.contingency) == ("CT151", True)
    notes = [e.detail for e in doc.events.filter(kind="note")]
    assert (why in notes[0]) if why else notes == []


def test_a_number_from_another_registers_block_is_renumbered(cashier, shift, register, warehouse, hammer, contingency, numbering):
    other = CashRegister.objects.create(code="CAJA2", name="Caja 2", warehouse=warehouse)
    NumberingResolution.objects.create(
        register=other, document_type="CONTINGENCY", number="2", issued_on=datetime.date(2026, 1, 1),
        valid_from=datetime.date(2026, 1, 1), valid_until=datetime.date(2027, 12, 31), prefix="CT2", range_from=1, range_to=100,
    )
    reserve(cashier, other)  # CT2 1–50: de la caja 2
    doc = offline_sale(cashier, shift, hammer, number=5).fiscal_documents.get()  # venta de la caja 1
    assert doc.code == "CT11"
    assert "no es de un bloque de la caja" in doc.events.get(kind="note").detail


def test_a_repeated_number_is_renumbered(cashier, shift, register, hammer, contingency, numbering):
    reserve(cashier, register)
    first = offline_sale(cashier, shift, hammer, number=3).fiscal_documents.get()
    second = offline_sale(cashier, shift, hammer, number=3).fiscal_documents.get()
    assert (first.code, second.code) == ("CT13", "CT151")
    assert "ya se usó" in second.events.get(kind="note").detail


def test_without_contingency_numbering_it_uses_the_pos_numbering(cashier, shift, hammer, numbering):
    doc = offline_sale(cashier, shift, hammer).fiscal_documents.get()
    assert (doc.code, doc.contingency) == ("CJ11", True)


def test_without_any_numbering_the_sale_is_kept_for_review(cashier, shift, hammer):
    sale = offline_sale(cashier, shift, hammer)
    sale.refresh_from_db()
    assert (sale.fiscal_documents.count(), sale.needs_review) == (0, True)


def test_invoice_asked_offline_gets_a_pos_document_and_a_note(cashier, shift, register, hammer, contingency, numbering, client_co):
    doc = offline_sale(cashier, shift, hammer, customer=client_co, invoice=True).fiscal_documents.get()
    assert (doc.kind, doc.customer) == (Kind.POS, client_co)
    assert "Se pidió factura sin conexión" in doc.events.get(kind="note").detail


def test_numbering_of_pos_and_contingency_cannot_cross(register):
    def resolution(document_type, prefix, start, end):
        return NumberingResolution(
            register=register, document_type=document_type, number="1", issued_on=datetime.date(2026, 1, 1),
            valid_from=datetime.date(2026, 1, 1), valid_until=datetime.date(2026, 12, 31), prefix=prefix, range_from=start, range_to=end,
        )
    resolution("POS", "CJ1", 1, 100).save()
    with pytest.raises(ValidationError, match="se cruza"):
        resolution("CONTINGENCY", "CJ1", 50, 150).full_clean(exclude=["next_number"])
    resolution("CONTINGENCY", "CJ1", 101, 150).full_clean(exclude=["next_number"])
    resolution("INVOICE", "CJ1", 50, 150).full_clean(exclude=["next_number"])  # la factura es otro documento


# --- plazo y envío -------------------------------------------------------------

def test_the_48_hours_count_from_arrival_and_the_queue_sends_it(cashier, shift, hammer, numbering, contingency):
    sale, _ = create_sale(
        user=cashier, shift=shift, client_uuid=uuid.uuid4(), offline=True,
        occurred_at=timezone.now() - timedelta(days=3),  # vendida hace 3 días, llegó ahora
        lines=[{"product": hammer, "quantity": Decimal("1"), "unit_price": Decimal("28000")}],
        payments=[{"method": "CASH", "amount": "28000"}],
    )
    doc = sale.fiscal_documents.get()
    assert alert(doc) is None
    assert alert(doc, doc.created_at + timedelta(hours=40)) == "due_soon"
    assert process_queue()["validated"] == 1
    doc.refresh_from_db()
    assert doc.status == FiscalDocument.Status.VALIDATED


def test_api_offline_sale_with_its_contingency_number(cashier, shift, register, hammer, contingency, numbering):
    reserve(cashier, register)
    body = {
        "client_uuid": str(uuid.uuid4()), "shift": shift.pk, "offline": True, "occurred_at": OCCURRED.isoformat(),
        "lines": [{"product": hammer.pk, "quantity": "1", "unit_price": "28000"}],
        "payments": [{"method": "CASH", "amount": "28000"}], "contingency_number": 12,
    }
    client = api(cashier)
    res = client.post("/api/sales/", body, format="json")
    assert res.status_code == 201, res.data
    docs = client.get(f"/api/sales/{res.data['id']}/").data["fiscal_documents"]
    assert [(d["code"], d["contingency"]) for d in docs] == [("CT112", True)]
    body.update(client_uuid=str(uuid.uuid4()), contingency_number=0)
    assert client.post("/api/sales/", body, format="json").status_code == 400
