"""Cola de envío de documentos electrónicos (spec 005, T4).

La corre `manage.py send_fiscal_documents` cada minuto. Envía los pendientes en el orden en que
se emitieron; una nota espera a que la DIAN valide el documento que corrige. Si el proveedor no
responde, el documento espera cada vez más (1, 2, 4… hasta 60 minutos) y el ciclo se corta para no
insistir contra un servicio caído.
"""
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from .documents import log, send_document
from .models import FiscalDocument
from .providers import get_provider

Status = FiscalDocument.Status
MAX_BACKOFF_MINUTES = 60
# Plazo de transmisión tras una falla (Res. 165 de 2023, art. 37) y aviso cuando quedan 12 horas.
DEADLINE = timedelta(hours=48)
DUE_SOON = timedelta(hours=12)


def backoff(attempts):
    return timedelta(minutes=min(2 ** max(attempts - 1, 0), MAX_BACKOFF_MINUTES))


def due_documents(now, limit=100):
    return (
        FiscalDocument.objects.filter(status=Status.PENDING)
        .filter(Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now))
        .filter(Q(corrects__isnull=True) | Q(corrects__status=Status.VALIDATED))
        .order_by("issued_at", "pk")[:limit]
    )


def process_queue(now=None, provider=None, limit=100):
    """Envía lo que toca ahora. Devuelve cuántos se validaron, rechazaron o no tuvieron respuesta."""
    now = now or timezone.now()
    provider = provider or get_provider()
    counts = {"validated": 0, "rejected": 0, "unavailable": 0}
    for document in due_documents(now, limit):
        document = send_document(document, provider)
        if document.status == Status.VALIDATED:
            counts["validated"] += 1
        elif document.status == Status.REJECTED:
            counts["rejected"] += 1
        else:
            document.next_attempt_at = now + backoff(document.attempts)
            document.save(update_fields=["next_attempt_at"])
            counts["unavailable"] += 1
            break  # sin servicio: el resto espera al próximo ciclo
    return counts


def deadline(document):
    return document.issued_at + DEADLINE


def alert(document, now=None):
    """'overdue' si un pendiente pasó el plazo, 'due_soon' si le quedan 12 horas o menos."""
    if document.status != Status.PENDING:
        return None
    left = deadline(document) - (now or timezone.now())
    if left < timedelta(0):
        return "overdue"
    return "due_soon" if left <= DUE_SOON else None


def retry(document, user):
    """El supervisor corrigió los datos (p. ej. del cliente): el rechazado vuelve a la cola."""
    if document.status != Status.REJECTED:
        raise ValueError("Solo se reintenta un documento rechazado.")
    document.status = Status.PENDING
    document.next_attempt_at = None
    document.save(update_fields=["status", "next_attempt_at"])
    log(document, "retry", f"Reintento pedido por {user.username}")
    return document
