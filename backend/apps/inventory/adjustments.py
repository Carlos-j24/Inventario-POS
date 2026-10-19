"""Ajustes de inventario (spec 006, T3).

Reglas:
- Lo pide bodega (inventory.receive, inventory.count o inventory.adjust) y lo aprueba quien tiene
  inventory.adjust, que puede aprobar los suyos (decisión 1). Se crea pendiente: la pantalla lo arma
  de una vez, así que no hay borrador editable.
- Motivos fijos (decisión 8). Daño, pérdida, uso interno y vencimiento solo sacan; sobrante solo
  entra; error de registro puede ir en los dos sentidos. "Conteo físico" lo genera el conteo (T5).
- Aprobar bloquea el ajuste y registra todos sus movimientos en una transacción: entran todos o
  ninguno, y dos aprobaciones a la vez no lo aplican dos veces.
- Una baja sale al costo promedio y no puede dejar el stock en negativo. Un sobrante entra al costo
  promedio; si el producto no tiene costo (promedio en 0), hay que indicarlo.
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.catalog.units import to_base_quantity

from .costing import COST_PLACES
from .models import Adjustment, AdjustmentLine, StockLevel, StockMovement
from .services import record_movement

Reason = Adjustment.Reason
Status = Adjustment.Status
OUT_ONLY = {Reason.DAMAGE, Reason.LOSS, Reason.INTERNAL_USE, Reason.EXPIRED}
IN_ONLY = {Reason.SURPLUS}
REQUESTERS = ("inventory.receive", "inventory.count", "inventory.adjust")


def _line(reason, item):
    """Valida una línea y la deja en unidad base con signo."""
    product, quantity = item["product"], Decimal(item["quantity"])
    unit = item.get("unit") or product.base_unit
    direction = item["direction"]
    if direction not in ("IN", "OUT"):
        raise ValidationError("Cada línea dice si entra (IN) o sale (OUT).")
    if quantity <= 0:
        raise ValidationError(f"{product.sku}: la cantidad debe ser mayor que cero.")
    if reason in OUT_ONLY and direction == "IN":
        raise ValidationError(f"{Reason(reason).label}: solo puede sacar mercancía.")
    if reason in IN_ONLY and direction == "OUT":
        raise ValidationError(f"{Reason(reason).label}: solo puede entrar mercancía.")
    base = to_base_quantity(product, quantity, unit)
    cost = item.get("unit_cost")
    if cost is not None:
        if direction == "OUT":
            raise ValidationError(f"{product.sku}: una salida sale al costo promedio; no lleva costo.")
        cost = (Decimal(cost) * quantity / base).quantize(COST_PLACES)  # el costo llega por la unidad elegida
    return AdjustmentLine(
        product=product, unit=unit, quantity=quantity,
        base_quantity=base if direction == "IN" else -base, unit_cost=cost,
    )


def create_adjustment(*, user, client_uuid, warehouse, reason, note, lines, system=False):
    """Crea un ajuste pendiente. Devuelve (ajuste, creado); con el mismo client_uuid, el que ya existe."""
    if reason == Reason.PHYSICAL_COUNT and not system:
        raise ValidationError("Los ajustes por conteo físico los genera el conteo al aprobarse.")
    if not (note or "").strip():
        raise ValidationError("Escribe una nota: qué pasó con la mercancía.")
    if not lines:
        raise ValidationError("El ajuste no tiene líneas.")
    built = [_line(reason, item) for item in lines]
    try:
        with transaction.atomic():
            adjustment = Adjustment.objects.create(
                client_uuid=client_uuid, warehouse=warehouse, reason=reason, note=note.strip(), requested_by=user,
            )
            for line in built:
                line.adjustment = adjustment
            AdjustmentLine.objects.bulk_create(built)
    except IntegrityError:
        # Reintento o doble clic con el mismo client_uuid: la restricción única devuelve el que ya existe.
        return Adjustment.objects.get(client_uuid=client_uuid), False
    return adjustment, True


def _lock_pending(adjustment):
    adjustment = Adjustment.objects.select_for_update().get(pk=adjustment.pk)
    if adjustment.status != Status.PENDING:
        raise ValidationError(f"El ajuste {adjustment.number} ya está {adjustment.get_status_display().lower()}.")
    return adjustment


def approve_adjustment(*, adjustment, user):
    """Registra todos los movimientos del ajuste o ninguno."""
    with transaction.atomic():
        adjustment = _lock_pending(adjustment)
        reference = f"{adjustment.number} {adjustment.get_reason_display()}"
        for line in adjustment.lines.select_related("product"):
            if line.base_quantity > 0 and line.unit_cost is None:
                level = StockLevel.objects.filter(product=line.product, warehouse=adjustment.warehouse).first()
                if level is None or level.average_cost == 0:
                    raise ValidationError(f"{line.product.sku} no tiene costo todavía: indica el costo del sobrante.")
            line.movement, _ = record_movement(
                kind=StockMovement.Kind.ADJUSTMENT, product=line.product, warehouse=adjustment.warehouse,
                quantity=line.base_quantity, unit_cost=line.unit_cost, user=user, reference=reference,
            )
            line.save(update_fields=["movement"])
        adjustment.status = Status.APPROVED
        adjustment.decided_by, adjustment.decided_at = user, timezone.now()
        adjustment.save(update_fields=["status", "decided_by", "decided_at"])
    return adjustment


def reject_adjustment(*, adjustment, user, note):
    """No mueve inventario; queda el motivo del rechazo."""
    if not (note or "").strip():
        raise ValidationError("Escribe por qué se rechaza.")
    with transaction.atomic():
        adjustment = _lock_pending(adjustment)
        adjustment.status = Status.REJECTED
        adjustment.decided_by, adjustment.decided_at = user, timezone.now()
        adjustment.rejection_note = note.strip()[:200]
        adjustment.save(update_fields=["status", "decided_by", "decided_at", "rejection_note"])
    return adjustment
