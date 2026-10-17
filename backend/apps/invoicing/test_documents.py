"""Documentos electrónicos por venta, anulación y devolución (spec 005, T3)."""
import os
import subprocess
import sys
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from django.core.exceptions import ValidationError
from django.test import override_settings
from rest_framework.test import APIClient

from apps.inventory.models import StockLevel
from apps.sales.models import Sale
from apps.sales.returns import create_return, void_sale
from apps.sales.services import create_sale

from .documents import send_document
from .models import FiscalDocument

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("stocked")]
enabled = override_settings(INVOICING_ENABLED=True)
Kind, Status = FiscalDocument.Kind, FiscalDocument.Status


def sell(user, shift, product, qty="2", **kwargs):
    sale, _ = create_sale(
        user=user, shift=shift, client_uuid=uuid.uuid4(), lines=[{"product": product, "quantity": Decimal(qty)}],
        payments=[{"method": "CASH", "amount": "10000000"}], **kwargs,
    )
    return sale


# --- emisión -----------------------------------------------------------------

def test_disabled_by_default_sales_have_no_fiscal_document(cashier, shift, hammer, numbering):
    assert sell(cashier, shift, hammer).fiscal_documents.count() == 0


@enabled
def test_a_sale_gets_a_pos_document_for_the_final_consumer(cashier, shift, hammer, numbering):
    first, second = sell(cashier, shift, hammer), sell(cashier, shift, hammer, qty="1")
    doc = first.fiscal_documents.get()
    assert (doc.kind, doc.code, doc.status, doc.customer.id_number) == (Kind.POS, "CJ11", Status.PENDING, "222222222222")
    assert (doc.subtotal, doc.tax, doc.total) == (first.subtotal, first.tax, first.total)
    assert doc.resolution.document_type == "POS"
    assert [e.kind for e in doc.events.all()] == ["created"]
    assert second.fiscal_documents.get().code == "CJ12"


@enabled
def test_identified_customer_without_invoice_gets_a_pos_document_in_their_name(cashier, shift, hammer, numbering, client_co):
    doc = sell(cashier, shift, hammer, customer=client_co).fiscal_documents.get()
    assert (doc.kind, doc.customer) == (Kind.POS, client_co)


@enabled
def test_invoice_on_request_uses_the_invoice_numbering(cashier, shift, hammer, numbering, client_co):
    doc = sell(cashier, shift, hammer, customer=client_co, invoice=True).fiscal_documents.get()
    assert (doc.kind, doc.code, doc.customer) == (Kind.INVOICE, "FE11", client_co)


@enabled
def test_invoice_for_the_final_consumer_is_refused_and_nothing_is_saved(cashier, shift, warehouse, hammer, numbering):
    with pytest.raises(ValidationError, match="identifica al cliente"):
        sell(cashier, shift, hammer, invoice=True)
    assert Sale.objects.count() == 0
    assert StockLevel.objects.get(product=hammer, warehouse=warehouse).quantity == 20
    assert sell(cashier, shift, hammer).fiscal_documents.get().code == "CJ11"  # no se gastó número


@enabled
def test_without_numbering_the_sale_fails_with_the_reason(cashier, shift, warehouse, hammer):
    with pytest.raises(ValidationError, match="no tiene resolución de numeración"):
        sell(cashier, shift, hammer)
    assert Sale.objects.count() == 0
    assert StockLevel.objects.get(product=hammer, warehouse=warehouse).quantity == 20


# --- notas -------------------------------------------------------------------

@enabled
def test_void_issues_an_adjustment_note_for_the_whole_sale(cashier, shift, hammer, numbering, make_user):
    sale = sell(cashier, shift, hammer)
    void_sale(sale=sale, user=make_user("super", "Supervisor"), reason="Cliente se arrepintió")
    original, note = sale.fiscal_documents.get(kind=Kind.POS), sale.fiscal_documents.get(kind=Kind.POS_ADJUSTMENT)
    assert (note.code, note.corrects, note.customer, note.total, note.subtotal, note.tax) == (
        "NA1", original, original.customer, sale.total, sale.subtotal, sale.tax,
    )
    assert "Cliente se arrepintió" in note.events.get().detail


@enabled
def test_voiding_an_invoice_issues_a_credit_note(cashier, shift, hammer, numbering, client_co, make_user):
    sale = sell(cashier, shift, hammer, customer=client_co, invoice=True)
    void_sale(sale=sale, user=make_user("super", "Supervisor"), reason="Error")
    note = sale.fiscal_documents.get(kind=Kind.CREDIT_NOTE)
    assert (note.code, note.corrects.kind, note.customer) == ("NC1", Kind.INVOICE, client_co)


@enabled
def test_each_partial_return_issues_its_own_note(cashier, shift, hammer, numbering, make_user):
    sale = sell(cashier, shift, hammer, qty="3")
    line = sale.lines.get()
    supervisor = make_user("super", "Supervisor")
    returns = [
        create_return(sale=sale, user=supervisor, shift=shift, lines=[{"sale_line": line, "quantity": "1"}],
                      refund_method="CASH", reason=f"Devolución {i}", client_uuid=uuid.uuid4())[0]
        for i in (1, 2)
    ]
    notes = list(sale.fiscal_documents.filter(kind=Kind.POS_ADJUSTMENT).order_by("number"))
    assert [n.code for n in notes] == ["NA1", "NA2"]
    assert [n.sale_return for n in notes] == returns
    assert notes[0].total == returns[0].total
    assert notes[0].subtotal + notes[0].tax == notes[0].total
    assert notes[0].subtotal == returns[0].lines.get().subtotal


def test_no_note_when_the_sale_had_no_document(cashier, shift, hammer, numbering, make_user):
    sale = sell(cashier, shift, hammer)  # facturación apagada al vender
    with enabled:
        void_sale(sale=sale, user=make_user("super", "Supervisor"), reason="Error")
    assert sale.fiscal_documents.count() == 0


# --- envío al proveedor ------------------------------------------------------

@enabled
def test_send_validates_with_cude_and_qr_once(cashier, shift, hammer, numbering):
    doc = sell(cashier, shift, hammer).fiscal_documents.get()
    doc = send_document(doc)
    assert (doc.status, doc.attempts, doc.last_error) == (Status.VALIDATED, 1, "")
    assert len(doc.cude) == 96 and int(doc.cude, 16) >= 0
    assert doc.qr_data.endswith(doc.cude)
    assert doc.validated_at is not None
    assert [e.kind for e in doc.events.all()] == ["created", "validated"]
    assert send_document(doc).attempts == 1  # ya validado: no se reenvía


@enabled
def test_note_cude_differs_from_the_document_it_corrects(cashier, shift, hammer, numbering, make_user):
    sale = sell(cashier, shift, hammer)
    original = send_document(sale.fiscal_documents.get())
    void_sale(sale=sale, user=make_user("super", "Supervisor"), reason="Error")
    note = send_document(sale.fiscal_documents.get(kind=Kind.POS_ADJUSTMENT))
    assert note.status == Status.VALIDATED
    assert note.cude != original.cude


@enabled
@override_settings(INVOICING_SIMULATED_MODE="reject")
def test_rejection_is_recorded(cashier, shift, hammer, numbering):
    doc = send_document(sell(cashier, shift, hammer).fiscal_documents.get())
    assert (doc.status, doc.cude) == (Status.REJECTED, "")
    assert "Rechazo simulado" in doc.last_error
    assert doc.events.last().kind == "rejected"


@enabled
@override_settings(INVOICING_SIMULATED_MODE="down")
def test_unavailable_provider_leaves_it_pending(cashier, shift, hammer, numbering):
    doc = send_document(sell(cashier, shift, hammer).fiscal_documents.get())
    doc = send_document(doc)
    assert (doc.status, doc.attempts) == (Status.PENDING, 2)
    assert "sin servicio" in doc.last_error
    assert [e.kind for e in doc.events.all()] == ["created", "unavailable", "unavailable"]


# --- API ---------------------------------------------------------------------

@enabled
def test_api_sale_with_invoice_shows_its_documents(cashier, shift, hammer, numbering, client_co):
    client = APIClient()
    client.force_authenticate(cashier)
    body = {"client_uuid": str(uuid.uuid4()), "shift": shift.pk, "lines": [{"product": hammer.pk, "quantity": "1"}],
            "payments": [{"method": "CASH", "amount": "28000"}], "customer": client_co.pk, "invoice": True}
    res = client.post("/api/sales/", body, format="json")
    assert res.status_code == 201, res.data
    docs = client.get(f"/api/sales/{res.data['id']}/").data["fiscal_documents"]
    assert [(d["kind"], d["code"], d["status"], d["customer"]) for d in docs] == [("INVOICE", "FE11", "PENDING", "Constructora SAS")]

    body.update(client_uuid=str(uuid.uuid4()), customer=None)
    res = client.post("/api/sales/", body, format="json")
    assert res.status_code == 400
    assert "identifica al cliente" in str(res.data)


def test_production_refuses_the_simulated_provider():
    env = {**os.environ, "DJANGO_DEBUG": "0", "DJANGO_SECRET_KEY": "x" * 50, "INVOICING_ENABLED": "1"}
    env.pop("INVOICING_PROVIDER", None)
    backend = Path(__file__).resolve().parents[2]
    result = subprocess.run([sys.executable, "-c", "import config.settings"], cwd=backend, env=env, capture_output=True, text=True)
    assert result.returncode != 0
    assert "proveedor real" in result.stderr
    env["INVOICING_PROVIDER"] = "otro.Proveedor"
    assert subprocess.run([sys.executable, "-c", "import config.settings"], cwd=backend, env=env).returncode == 0
