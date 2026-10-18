"""Emisión y envío de documentos electrónicos (spec 005, T3).

Los documentos se crean dentro de la transacción de la venta, la anulación o la devolución:
si esta falla, no queda documento ni se gasta número. El envío al proveedor es aparte (cola, T4).
"""
import logging

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.customers.models import Customer
from apps.customers.rules import FINAL_CONSUMER_NUMBER
from apps.sales.models import Sale

from .mail import email_customer
from .models import ContingencyBlock, FiscalDocument, FiscalEvent, InternalCounter, NumberingResolution
from .numbering import NumberingError, take_number
from .providers import ProviderUnavailable, get_provider

Kind = FiscalDocument.Kind
logger = logging.getLogger(__name__)
NOTE_FOR = {Kind.POS: Kind.POS_ADJUSTMENT, Kind.INVOICE: Kind.CREDIT_NOTE}
NOTE_PREFIX = {Kind.POS_ADJUSTMENT: "NA", Kind.CREDIT_NOTE: "NC"}


def log(document, kind, detail=""):
    FiscalEvent.objects.create(document=document, kind=kind, detail=detail)


def final_consumer():
    return Customer.objects.get(id_number=FINAL_CONSUMER_NUMBER)


def issue_for_sale(sale, *, customer=None, invoice=False, contingency_number=None):
    """DE-POS por defecto o factura si el cliente la pide (spec 005, decisión 2). None si no aplica.

    Una venta sin conexión recibe su documento de contingencia (T5).
    """
    if not settings.INVOICING_ENABLED:
        return None
    customer = customer or final_consumer()
    if sale.offline:
        return issue_contingency(sale, customer, contingency_number, invoice_requested=invoice)
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


def _contingency_number(register, number):
    """La resolución del número que puso el POS, si viene de un bloque de la caja y no está usado."""
    if number is None:
        return None
    block = (
        ContingencyBlock.objects.filter(register=register, start__lte=number, end__gte=number)
        .select_related("resolution").first()
    )
    if block is None:
        return None
    used = FiscalDocument.objects.filter(kind=Kind.POS, prefix=block.resolution.prefix, number=number).exists()
    return None if used else block.resolution


def issue_contingency(sale, customer, number=None, *, invoice_requested=False):
    """Documento POS de una venta hecha sin conexión (Res. 165 de 2023, art. 37, 2.2).

    El tiquete ya se entregó con el número del bloque de la caja; aquí se genera el documento
    electrónico para transmitirlo dentro de 48 horas desde que llegó. Una venta sin conexión nunca
    se rechaza: si el número no sirve, se numera ahora (y queda en el historial); si no hay
    numeración, la venta queda para revisión sin documento.
    """
    register = sale.shift.register
    notes = []
    resolution = _contingency_number(register, number)
    if resolution is None:
        if number is not None:
            notes.append(f"El número de contingencia {number} no es de un bloque de la caja o ya se usó: se numeró al recibir la venta.")
        for document_type in (NumberingResolution.DocumentType.CONTINGENCY, NumberingResolution.DocumentType.POS):
            try:
                resolution, number = take_number(register, document_type)
                break
            except NumberingError:
                continue
        else:
            logger.warning("Venta %s sin conexión sin documento: la caja %s no tiene numeración.", sale.number, register.code)
            Sale.objects.filter(pk=sale.pk).update(needs_review=True)
            return None
    if invoice_requested:
        notes.append("Se pidió factura sin conexión: se emitió documento POS de contingencia.")
    document = FiscalDocument.objects.create(
        kind=Kind.POS, contingency=True, sale=sale, customer=customer, resolution=resolution,
        prefix=resolution.prefix, number=number, issued_at=sale.occurred_at,
        subtotal=sale.subtotal, tax=sale.tax, total=sale.total,
    )
    log(document, "created", f"Venta {sale.number} sin conexión (contingencia)")
    for note in notes:
        log(document, "note", note)
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


def _notify(pk):
    """Correo al cliente, fuera de la transacción del envío: si falla, el documento sigue validado."""
    document = FiscalDocument.objects.select_related("customer").get(pk=pk)
    if email_customer(document):
        log(document, "emailed", document.customer.email)


def send_document(document, provider=None):
    """Envía un documento pendiente al proveedor y guarda el resultado. Lo usa la cola (T4).

    Un rechazo queda registrado para el supervisor; si no hubo respuesta, sigue pendiente.
    """
    provider = provider or get_provider()
    with transaction.atomic():
        document = (
            FiscalDocument.objects.select_for_update(of=("self",))  # PostgreSQL no bloquea el lado opcional de un JOIN
            .select_related("customer", "corrects").get(pk=document.pk)
        )
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
            transaction.on_commit(lambda: _notify(document.pk))
        else:
            document.status = FiscalDocument.Status.REJECTED
            document.last_error = result.message
            log(document, "rejected", result.message)
        document.save()
    return document
