"""Cola de envío y bandeja del supervisor (spec 005, T4)."""
from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.sales.returns import void_sale

from .models import FiscalDocument
from .queue import alert, backoff, process_queue, retry
from .serializers import FiscalDocumentRowSerializer
from .test_documents import sell

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("stocked", "numbering")]
Status = FiscalDocument.Status


@pytest.fixture(autouse=True)
def invoicing_on(settings):
    settings.INVOICING_ENABLED = True


def docs():
    return list(FiscalDocument.objects.order_by("pk"))


@pytest.mark.parametrize("attempts, minutes", [(1, 1), (2, 2), (3, 4), (6, 32), (7, 60), (12, 60)])
def test_backoff_grows_up_to_an_hour(attempts, minutes):
    assert backoff(attempts) == timedelta(minutes=minutes)


def test_queue_sends_pending_documents_in_order(cashier, shift, hammer):
    sell(cashier, shift, hammer), sell(cashier, shift, hammer)
    assert process_queue() == {"validated": 2, "rejected": 0, "unavailable": 0}
    assert [d.status for d in docs()] == [Status.VALIDATED, Status.VALIDATED]
    assert process_queue() == {"validated": 0, "rejected": 0, "unavailable": 0}


def test_limit(cashier, shift, hammer):
    for _ in range(3):
        sell(cashier, shift, hammer, qty="1")
    assert process_queue(limit=2)["validated"] == 2
    assert [d.status for d in docs()] == [Status.VALIDATED, Status.VALIDATED, Status.PENDING]


def test_a_note_waits_until_its_document_is_validated(cashier, shift, hammer, make_user):
    sale = sell(cashier, shift, hammer)
    void_sale(sale=sale, user=make_user("super", "Supervisor"), reason="Error")
    _, note = docs()
    assert FiscalDocumentRowSerializer(note).data["waiting_for"] == "CJ11"
    assert process_queue()["validated"] == 1  # solo el original
    original, note = docs()
    assert (original.status, note.status) == (Status.VALIDATED, Status.PENDING)
    assert FiscalDocumentRowSerializer(note).data["waiting_for"] is None  # ya puede salir
    assert process_queue()["validated"] == 1
    note.refresh_from_db()
    assert note.status == Status.VALIDATED


def test_rejected_document_is_reported_and_blocks_its_note(cashier, shift, hammer, make_user):
    sale = sell(cashier, shift, hammer)
    void_sale(sale=sale, user=make_user("super", "Supervisor"), reason="Error")
    with override_settings(INVOICING_SIMULATED_MODE="reject"):
        assert process_queue()["rejected"] == 1
    assert process_queue() == {"validated": 0, "rejected": 0, "unavailable": 0}  # la nota espera
    client = APIClient()
    client.force_authenticate(make_user("super2", "Supervisor"))
    rows = {r["code"]: r for r in client.get("/api/invoicing/documents/").data["results"]}
    assert rows["NA1"]["waiting_for"] == "CJ11"
    assert rows["CJ11"]["status"] == "REJECTED"
    assert "Rechazo simulado" in rows["CJ11"]["last_error"]


@override_settings(INVOICING_SIMULATED_MODE="down")
def test_unavailable_provider_backs_off_and_stops_the_cycle(cashier, shift, hammer):
    sell(cashier, shift, hammer), sell(cashier, shift, hammer)
    now = timezone.now()
    assert process_queue(now=now) == {"validated": 0, "rejected": 0, "unavailable": 1}
    first, second = docs()
    assert (first.attempts, first.next_attempt_at, second.attempts) == (1, now + timedelta(minutes=1), 0)

    process_queue(now=now + timedelta(seconds=30))  # el primero espera; se intenta el segundo
    first, second = docs()
    assert (first.attempts, second.attempts) == (1, 1)

    process_queue(now=now + timedelta(seconds=61))
    first = docs()[0]
    assert (first.attempts, first.next_attempt_at) == (2, now + timedelta(seconds=61) + timedelta(minutes=2))


def test_alerts_for_the_48_hour_deadline(cashier, shift, hammer):
    doc = sell(cashier, shift, hammer).fiscal_documents.get()
    now = doc.issued_at
    assert alert(doc, now) is None
    assert alert(doc, now + timedelta(hours=36)) == "due_soon"
    assert alert(doc, now + timedelta(hours=35, minutes=59)) is None
    assert alert(doc, now + timedelta(hours=48)) == "due_soon"  # justo en el plazo todavía no venció
    assert alert(doc, now + timedelta(hours=48, seconds=1)) == "overdue"
    doc.status = Status.VALIDATED
    assert alert(doc, now + timedelta(hours=50)) is None


def test_retry_puts_a_rejected_document_back_in_the_queue(cashier, shift, hammer, make_user):
    doc = sell(cashier, shift, hammer).fiscal_documents.get()
    supervisor = make_user("super", "Supervisor")
    with pytest.raises(ValueError):
        retry(doc, supervisor)
    with override_settings(INVOICING_SIMULATED_MODE="reject"):
        process_queue()
    doc.refresh_from_db()
    doc.next_attempt_at = timezone.now() + timedelta(hours=1)
    doc.save()
    retry(doc, supervisor)
    doc.refresh_from_db()
    assert (doc.status, doc.next_attempt_at) == (Status.PENDING, None)
    assert "super" in doc.events.last().detail
    assert process_queue()["validated"] == 1


def test_command(cashier, shift, hammer):
    sell(cashier, shift, hammer)
    out = StringIO()
    call_command("send_fiscal_documents", stdout=out)
    assert "Validados: 1" in out.getvalue()
    with override_settings(INVOICING_ENABLED=False):
        out = StringIO()
        call_command("send_fiscal_documents", stdout=out)
        assert "apagada" in out.getvalue()


# --- API de la bandeja -------------------------------------------------------

def test_inbox_summary_and_filters(cashier, shift, hammer, make_user):
    for _ in range(5):
        sell(cashier, shift, hammer, qty="1")
    first, second, third, fourth, fifth = docs()  # el quinto queda pendiente y reciente
    process_queue(limit=1)  # valida el primero
    with override_settings(INVOICING_SIMULATED_MODE="reject"):
        process_queue(limit=1)  # rechaza el segundo
    now = timezone.now()
    FiscalDocument.objects.filter(pk=third.pk).update(issued_at=now - timedelta(hours=49))
    FiscalDocument.objects.filter(pk=fourth.pk).update(issued_at=now - timedelta(hours=40))

    client = APIClient()
    client.force_authenticate(make_user("super", "Supervisor"))
    data = client.get("/api/invoicing/documents/").data
    assert data["summary"] == {"pending": 3, "rejected": 1, "overdue": 1, "due_soon": 1}
    assert {r["code"]: r["alert"] for r in data["results"]} == {"CJ12": None, "CJ13": "overdue", "CJ14": "due_soon", "CJ15": None}
    assert [r["code"] for r in client.get("/api/invoicing/documents/", {"status": "VALIDATED"}).data["results"]] == ["CJ11"]
    assert [r["code"] for r in client.get("/api/invoicing/documents/", {"status": "REJECTED"}).data["results"]] == ["CJ12"]

    detail = client.get(f"/api/invoicing/documents/{second.pk}/").data
    assert [e["kind"] for e in detail["events"]] == ["created", "rejected"]
    assert (detail["sale_number"], detail["register"], detail["customer"]) == (second.sale.number, "CAJA1", "Consumidor final")


def test_retry_endpoint_and_permissions(cashier, shift, hammer, make_user):
    doc = sell(cashier, shift, hammer).fiscal_documents.get()
    client = APIClient()
    client.force_authenticate(cashier)
    assert client.get("/api/invoicing/documents/").status_code == 403  # Caja no tiene reports.view
    assert client.post(f"/api/invoicing/documents/{doc.pk}/retry/").status_code == 403

    client.force_authenticate(make_user("jefe", "Jefe de bodega"))  # ve reportes, pero no anula
    assert client.get("/api/invoicing/documents/").status_code == 200
    assert client.post(f"/api/invoicing/documents/{doc.pk}/retry/").status_code == 403

    client.force_authenticate(make_user("super", "Supervisor"))
    res = client.post(f"/api/invoicing/documents/{doc.pk}/retry/")
    assert res.status_code == 400
    assert "rechazado" in res.data["detail"]
    with override_settings(INVOICING_SIMULATED_MODE="reject"):
        process_queue()
    res = client.post(f"/api/invoicing/documents/{doc.pk}/retry/")
    assert (res.status_code, res.data["status"], res.data["events"][-1]["kind"]) == (200, "PENDING", "retry")
