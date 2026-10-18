"""Tiquete de 80 mm, envío inmediato y correo al cliente (spec 005, T6)."""
import uuid
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.customers.models import Customer
from apps.sales.services import create_sale

from . import mail
from .documents import send_document
from .models import Business, FiscalDocument
from .ticket import ticket_for_sale

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("stocked", "numbering")]
Status = FiscalDocument.Status


@pytest.fixture
def invoicing_on(settings):
    settings.INVOICING_ENABLED = True


def sell(user, shift, product, qty="2", payments=None, **kwargs):
    sale, _ = create_sale(
        user=user, shift=shift, client_uuid=uuid.uuid4(), lines=[{"product": product, "quantity": Decimal(qty)}],
        payments=payments or [{"method": "CASH", "amount": "60000"}], **kwargs,
    )
    return sale


def api(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


# --- tiquete -----------------------------------------------------------------

def test_without_invoicing_the_ticket_says_it_has_no_fiscal_document(cashier, shift, hammer):
    t = ticket_for_sale(sell(cashier, shift, hammer))
    assert (t["title"], t["code"], t["status"], t["qr_svg"], t["resolution"], t["document_id"]) == ("Comprobante de venta", None, None, None, None, None)
    assert "no está activa" in t["notes"][0]
    assert t["lines"] == [{"name": "Martillo 16 oz", "quantity": "2.000", "unit": "und", "unit_price": "28000.00", "total": "56000.00"}]
    assert (t["subtotal"], t["tax"], t["total"]) == ("47058.82", "8941.18", "56000.00")
    assert t["taxes"] == [{"rate": "19", "base": "47058.82", "tax": "8941.18"}]
    assert (t["payments"], t["change"]) == ([{"label": "Efectivo", "amount": "60000.00"}], "4000.00")
    assert (t["register"], t["cashier"], t["customer"]) == ("CAJA1", "caja1", None)


@pytest.mark.usefixtures("invoicing_on")
def test_pending_then_validated_ticket(cashier, shift, hammer):
    sale = sell(cashier, shift, hammer)
    t = ticket_for_sale(sale)
    assert (t["title"], t["code"], t["status"], t["qr_svg"], t["cude"]) == ("Documento equivalente electrónico POS", "CJ11", "PENDING", None, None)
    assert t["notes"] == ["Pendiente de validación por la DIAN."]
    assert (t["customer"], t["document_id"]) == (None, sale.fiscal_documents.get().pk)  # consumidor final: no se imprime
    assert t["resolution"] == "Resolución DIAN 18764 del 2026-01-01: CJ11 a CJ15000, vigente hasta 2027-12-31"
    send_document(sale.fiscal_documents.get())
    t = ticket_for_sale(sale)
    assert t["status"] == "VALIDATED"
    assert t["qr_svg"].startswith("<svg") and len(t["cude"]) == 96
    assert t["notes"] == ["Documento validado por la DIAN"]


@pytest.mark.usefixtures("invoicing_on")
def test_invoice_ticket_shows_the_customer(cashier, shift, hammer, client_co, settings):
    sale = sell(cashier, shift, hammer, customer=client_co, invoice=True)
    t = ticket_for_sale(sale)
    assert (t["title"], t["code"]) == ("Factura electrónica de venta", "FE11")
    assert t["customer"] == {"name": "Constructora SAS", "document": "NIT 800197268-4"}
    settings.INVOICING_SIMULATED_MODE = "reject"
    send_document(sale.fiscal_documents.get())
    assert "Rechazado" in ticket_for_sale(sale)["notes"][0]


@pytest.mark.usefixtures("invoicing_on")
def test_contingency_and_excluded_lines(cashier, shift, hammer, cable):
    hammer.tax_rate, hammer.vat_excluded = "0", True
    hammer.save()
    sale, _ = create_sale(
        user=cashier, shift=shift, client_uuid=uuid.uuid4(), offline=True,
        lines=[{"product": hammer, "quantity": Decimal("1"), "unit_price": Decimal("28000")},
               {"product": cable, "quantity": Decimal("10"), "unit_price": Decimal("3200")}],
        payments=[{"method": "CARD", "amount": "60000"}],
    )
    t = ticket_for_sale(sale)
    assert t["notes"][0].startswith("Emitido en contingencia")
    assert t["taxes"] == [{"rate": "19", "base": "26890.76", "tax": "5109.24"}, {"rate": "excluido", "base": "28000.00", "tax": "0.00"}]
    assert (t["payments"], t["change"]) == ([{"label": "Tarjeta", "amount": "60000.00"}], "0.00")


def test_ticket_api_and_permissions(cashier, shift, hammer, make_user):
    sale = sell(cashier, shift, hammer)
    assert api(cashier).get(f"/api/invoicing/ticket/{sale.pk}/").data["sale_number"] == sale.number
    assert api(make_user("bodega", "Auxiliar de bodega")).get(f"/api/invoicing/ticket/{sale.pk}/").status_code == 403
    assert api(cashier).get("/api/invoicing/ticket/999999/").status_code == 404


# --- datos del negocio -------------------------------------------------------

def test_business_data_with_computed_check_digit(cashier):
    business = Business.load()
    business.name, business.nit, business.tax_regime = "Ferretería El Tornillo SAS", "800.197.268", "Responsable de IVA"
    business.full_clean()
    business.save()
    data = api(cashier).get("/api/invoicing/business/").data
    assert (data["name"], data["nit"], data["tax_regime"]) == ("Ferretería El Tornillo SAS", "800197268-4", "Responsable de IVA")
    assert Business.load().pk == business.pk  # un solo registro
    assert Business.objects.count() == 1


# --- envío inmediato ---------------------------------------------------------

@pytest.mark.usefixtures("invoicing_on")
def test_send_now_validates_or_leaves_it_for_the_queue(cashier, shift, hammer, make_user, settings):
    doc = sell(cashier, shift, hammer).fiscal_documents.get()
    res = api(cashier).post(f"/api/invoicing/documents/{doc.pk}/send/")
    assert (res.status_code, res.data["status"]) == (200, "VALIDATED")

    settings.INVOICING_SIMULATED_MODE = "down"
    doc = sell(cashier, shift, hammer).fiscal_documents.get()
    res = api(cashier).post(f"/api/invoicing/documents/{doc.pk}/send/")
    assert res.data["status"] == "PENDING" and "sin servicio" in res.data["last_error"]
    doc.refresh_from_db()
    assert doc.next_attempt_at is not None  # la cola lo reintenta después
    assert api(make_user("vende", "Ventas")).post(f"/api/invoicing/documents/{doc.pk}/send/").status_code == 403


# --- correo ------------------------------------------------------------------

@pytest.mark.usefixtures("invoicing_on")
def test_customer_with_email_receives_the_validated_document(cashier, shift, hammer, client_co, mailoutbox, django_capture_on_commit_callbacks):
    doc = sell(cashier, shift, hammer, customer=client_co, invoice=True).fiscal_documents.get()
    with django_capture_on_commit_callbacks(execute=True):
        doc = send_document(doc)
    assert len(mailoutbox) == 1
    message = mailoutbox[0]
    assert message.to == ["compras@ejemplo.co"]
    assert "FE11" in message.subject and doc.cude in message.body and doc.qr_data in message.body
    assert doc.events.last().kind == "emailed"


@pytest.mark.usefixtures("invoicing_on")
def test_no_email_without_address_or_for_the_final_consumer(cashier, shift, hammer, mailoutbox, django_capture_on_commit_callbacks):
    no_mail = Customer.objects.create(id_type="13", id_number="1020304050", name="Ana")
    for customer in (None, no_mail):
        doc = sell(cashier, shift, hammer, customer=customer).fiscal_documents.get()
        with django_capture_on_commit_callbacks(execute=True):
            send_document(doc)
    assert mailoutbox == []
    fc = Customer.objects.get(id_number="222222222222")
    Customer.objects.filter(pk=fc.pk).update(email="nadie@ejemplo.co")
    doc = sell(cashier, shift, hammer).fiscal_documents.get()
    with django_capture_on_commit_callbacks(execute=True):
        send_document(doc)
    assert mailoutbox == []


@pytest.mark.usefixtures("invoicing_on")
def test_a_failed_email_keeps_the_document_validated(cashier, shift, hammer, client_co, monkeypatch, django_capture_on_commit_callbacks):
    def broken(*args, **kwargs):
        raise OSError("SMTP caído")

    monkeypatch.setattr(mail, "send_mail", broken)
    doc = sell(cashier, shift, hammer, customer=client_co).fiscal_documents.get()
    with django_capture_on_commit_callbacks(execute=True):
        send_document(doc)
    doc.refresh_from_db()
    assert doc.status == Status.VALIDATED
    assert "emailed" not in [e.kind for e in doc.events.all()]
