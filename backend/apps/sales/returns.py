"""Anulaciones y devoluciones. Nada se borra: el stock vuelve con movimientos de devolución.

- Anular: deshace la venta completa. Solo mientras su turno siga abierto, porque el arqueo
  de un turno cerrado ya no puede cambiar.
- Devolver: total o parcial, en cualquier momento; el dinero sale del turno abierto.
- Revisar: dejar constancia de quién atendió una venta marcada (needs_review).
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from apps.cash.models import Refund, Shift
from apps.inventory.models import StockMovement
from apps.inventory.services import record_movement
from apps.invoicing.documents import issue_for_return, issue_for_void

from .models import Sale, SaleReturn, SaleReturnLine
from .services import money, split_tax

RETURN = StockMovement.Kind.RETURN


def _lock_sale(sale):
    sale = Sale.objects.select_for_update().get(pk=sale.pk)
    if sale.status != Sale.Status.COMPLETED:
        raise ValidationError(f"La venta {sale.number} está anulada.")
    return sale


def _lock_open_shift(shift, message):
    shift = Shift.objects.select_for_update().get(pk=shift.pk)
    if shift.status != Shift.Status.OPEN:
        raise ValidationError(message)
    return shift


def void_sale(*, sale, user, reason):
    """Anula una venta completa: devuelve todo el stock y saca sus pagos del arqueo."""
    if not reason.strip():
        raise ValidationError("Indica el motivo de la anulación.")
    with transaction.atomic():
        sale = _lock_sale(sale)
        _lock_open_shift(
            sale.shift, f"El turno de la venta {sale.number} ya cerró: registra una devolución."
        )
        if sale.returns.exists():
            raise ValidationError(f"La venta {sale.number} tiene devoluciones: no se puede anular.")
        for line in sale.lines.select_related("product", "unit"):
            record_movement(
                kind=RETURN, product=line.product, warehouse=sale.warehouse, quantity=line.quantity,
                unit=line.unit, user=user, reference=f"Anulación {sale.number}",
                unit_cost=line.movement.unit_cost,  # vuelve al costo con que salió (spec 004)
            )
        sale.status = Sale.Status.VOIDED
        sale.voided_by = user
        sale.voided_at = timezone.now()
        sale.void_reason = reason
        sale.save(update_fields=["status", "voided_by", "voided_at", "void_reason"])
        issue_for_void(sale)
    return sale


def create_return(*, sale, user, shift, lines, refund_method, reason, client_uuid):
    """Registra una devolución y su reembolso. Devuelve (devolución, creada).

    lines: dicts con sale_line y quantity (en la unidad en que se vendió).
    """
    existing = SaleReturn.objects.filter(client_uuid=client_uuid).first()
    if existing:
        return existing, False
    if not lines:
        raise ValidationError("La devolución no tiene líneas.")
    if not reason.strip():
        raise ValidationError("Indica el motivo de la devolución.")
    try:
        return _create_return(sale, user, shift, lines, refund_method, reason, client_uuid), True
    except IntegrityError:
        existing = SaleReturn.objects.filter(client_uuid=client_uuid).first()
        if existing is None:
            raise
        return existing, False


def _create_return(sale, user, shift, lines, refund_method, reason, client_uuid):
    with transaction.atomic():
        sale = _lock_sale(sale)
        shift = _lock_open_shift(shift, "El reembolso necesita un turno abierto.")
        sale_return = SaleReturn.objects.create(
            client_uuid=client_uuid, sale=sale, shift=shift, user=user, reason=reason, total=0,
        )
        for item in lines:
            line = item["sale_line"]
            qty = Decimal(item["quantity"])
            if line.sale_id != sale.pk:
                raise ValidationError("La línea no pertenece a esta venta.")
            if qty <= 0:
                raise ValidationError("Las cantidades deben ser positivas.")
            already = line.returned_quantity()
            if already + qty > line.quantity:
                raise ValidationError(
                    f"{line.product.sku}: se vendieron {line.quantity} y ya se devolvieron {already}."
                )
            if already + qty == line.quantity:
                # Última devolución de la línea: se reembolsa el resto exacto, sin centavos perdidos.
                refunded = line.return_lines.aggregate(t=Sum("total"))["t"] or 0
                total = line.total - refunded
            else:
                total = money(line.total * qty / line.quantity)
            subtotal, tax = split_tax(total, line.tax_rate)
            movement, _ = record_movement(
                kind=RETURN, product=line.product, warehouse=sale.warehouse, quantity=qty,
                unit=line.unit, user=user, reference=f"Devolución de {sale.number}",
                unit_cost=line.movement.unit_cost,  # vuelve al costo con que salió (spec 004)
            )
            SaleReturnLine.objects.create(
                sale_return=sale_return, sale_line=line, quantity=qty,
                subtotal=subtotal, tax=tax, total=total, movement=movement,
            )
            sale_return.total += total
        sale_return.save(update_fields=["total"])
        Refund.objects.create(sale_return=sale_return, shift=shift, method=refund_method, amount=sale_return.total)
        StockMovement.objects.filter(return_line__sale_return=sale_return).update(
            reference=f"Devolución {sale_return.number} de {sale.number}"
        )
        issue_for_return(sale_return)
    return sale_return


def mark_reviewed(*, sale, user, note=""):
    """Marca como atendida una venta que quedó para revisión. La marca needs_review se conserva."""
    with transaction.atomic():
        sale = Sale.objects.select_for_update().get(pk=sale.pk)
        if not sale.needs_review:
            raise ValidationError(f"La venta {sale.number} no está marcada para revisión.")
        if sale.reviewed_at:
            raise ValidationError(f"La venta {sale.number} ya fue revisada.")
        sale.reviewed_by = user
        sale.reviewed_at = timezone.now()
        sale.review_note = note
        sale.save(update_fields=["reviewed_by", "reviewed_at", "review_note"])
    return sale
