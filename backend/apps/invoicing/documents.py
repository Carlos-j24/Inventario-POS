"""Emisión y envío de documentos electrónicos (spec 005, T3).

Los documentos se crean dentro de la transacción de la venta, la anulación o la devolución:
si esta falla, no queda documento ni se gasta número. El envío al proveedor es aparte (cola, T4).
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.customers.models import Customer
from apps.customers.rules import FINAL_CONSUMER_NUMBER

from .models import FiscalDocument, FiscalEvent, InternalCounter
from .numbering import NumberingError, take_number
from .providers import ProviderUnavailable, get_provider

Kind = FiscalDocument.Kind
NOTE_FOR = {Kind.POS: Kind.POS_ADJUSTMENT, Kind.INVOICE: Kind.CREDIT_NOTE}
NOTE_PREFIX = {Kind.POS_ADJUSTMENT: "NA", Kind.CREDIT_NOTE: "NC"}


def log(document, kind, detail=""):
    FiscalEvent.objects.create(document=document, kind=kind, detail=detail)


def final_consumer():
    return Customer.objects.get(id_number=FINAL_CONSUMER_NUMBER)


def issue_for_sale(sale, *, customer=None, invoice=False):
    """DE-POS por defecto o factura si el cliente la pide (spec 005, decisión 2). None si no aplica.

    Las ventas sin conexión quedan para la contingencia (T5).
    """
    if not settings.INVOICING_ENABLED or sale.offline:
        return None
    customer = customer or final_consumer()
    if invoice and customer.is_final_consumer:
        raise ValidationError("Para la factura electrónica identifica al cliente: el consumidor final no puede recibirla.")
    kind = Kind.INVOICE if invoice else Kind.POS
    try:
        resolution, number = take_number(sale.shift.register, kind)
    except NumberingError as err:
        raise ValidationError(str(err)) from err
    document = FiscalDocument.objects.create(
        kind=kind, sale=sale, customer=customer, resolution=resolution, prefix=resolution.prefix, number=number,
        issued_at=timezone.now(), subtotal=sale.subtotal, tax=sale.tax, total=sale.total,
    )
    log(document, "created", f"Venta {sale.number}")
    return document


def _next_internal(key):
    counter = InternalCounter.objects.select_for_update().get(key=key)
    number = counter.next_number
    counter.next_number = number + 1
    counter.save(update_fields=["next_number"])
    return number


def _issue_note(sale, *, subtotal, tax, total, detail, sale_return=None):
    """Nota de ajuste (DE-POS) o nota crédito (factura) que corrige el documento de la venta."""
    original = sale.fiscal_documents.filter(kind__in=NOTE_FOR).first()
    if original is None:
        return None  # venta sin documento fiscal (facturación apagada o venta sin conexión)
    kind = NOTE_FOR[original.kind]
    with transaction.atomic():
        document = FiscalDocument.objects.create(
            kind=kind, sale=sale, sale_return=sale_return, corrects=original, customer=original.customer,
            prefix=NOTE_PREFIX[kind], number=_next_internal(kind), issued_at=timezone.now(),
            subtotal=subtotal, tax=tax, total=total,
        )
        log(document, "created", detail)
    return document


def issue_for_void(sale):
    """La anulación corrige el documento por el total de la venta."""
    return _issue_note(sale, subtotal=sale.subtotal, tax=sale.tax, total=sale.total,
                       detail=f"Anulación de {sale.number}: {sale.void_reason}")


def issue_for_return(sale_return):
    """Una devolución (parcial o total) corrige el documento por lo devuelto."""
    sums = sale_return.lines.aggregate(subtotal=Sum("subtotal"), tax=Sum("tax"), total=Sum("total"))
    return _issue_note(sale_return.sale, sale_return=sale_return, subtotal=sums["subtotal"], tax=sums["tax"],
                       total=sums["total"], detail=f"Devolución {sale_return.number}: {sale_return.reason}")


def send_document(document, provider=None):
    """Envía un documento pendiente al proveedor y guarda el resultado. Lo usa la cola (T4).

    Un rechazo queda registrado para el supervisor; si no hubo respuesta, sigue pendiente.
    """
    provider = provider or get_provider()
    with transaction.atomic():
        document = FiscalDocument.objects.select_for_update().select_related("customer", "corrects").get(pk=document.pk)
        if document.status != FiscalDocument.Status.PENDING:
            return document
        document.attempts += 1
        try:
            result = provider.send(document)
        except ProviderUnavailable as err:
            document.last_error = str(err)
            document.save(update_fields=["attempts", "last_error"])
            log(document, "unavailable", str(err))
            return document
        if result.validated:
            document.status = FiscalDocument.Status.VALIDATED
            document.cude, document.qr_data, document.provider_id = result.cude, result.qr_data, result.provider_id
            document.validated_at = timezone.now()
            document.last_error = ""
            log(document, "validated", f"{provider.name}: {result.cude}")
        else:
            document.status = FiscalDocument.Status.REJECTED
            document.last_error = result.message
            log(document, "rejected", result.message)
        document.save()
    return document
