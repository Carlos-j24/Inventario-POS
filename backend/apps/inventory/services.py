"""Único punto de entrada para mover inventario.

Toda entrada, venta, devolución o ajuste pasa por record_movement: escribe el movimiento
y actualiza el saldo en la misma transacción, con el saldo bloqueado para evitar carreras.
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.catalog.units import to_base_quantity

from .costing import COST_PLACES, next_average
from .models import StockLevel, StockMovement

Kind = StockMovement.Kind

INBOUND = {Kind.RECEIPT, Kind.RETURN, Kind.TRANSFER_IN}
OUTBOUND = {Kind.SALE, Kind.TRANSFER_OUT}


class InsufficientStock(ValidationError):
    pass


def record_movement(
    *,
    kind,
    product,
    warehouse,
    quantity,
    user,
    unit=None,
    unit_cost=None,
    reference="",
    client_uuid=None,
    occurred_at=None,
    allow_negative=False,
):
    """Registra un movimiento y devuelve (movimiento, creado).

    quantity va en la unidad indicada (o la base) y es positiva, salvo en ajustes,
    donde el signo dice si entra o sale. Con client_uuid repetido devuelve el
    movimiento ya registrado sin tocar el stock (reintentos del modo sin conexión).
    """
    if client_uuid:
        existing = StockMovement.objects.filter(client_uuid=client_uuid).first()
        if existing:
            return existing, False

    base_qty = to_base_quantity(product, quantity, unit)
    if base_qty == 0:
        raise ValidationError("La cantidad no puede ser cero.")
    if kind in INBOUND | OUTBOUND and base_qty < 0:
        raise ValidationError("La cantidad debe ser positiva; el tipo de movimiento define el signo.")
    signed = -base_qty if kind in OUTBOUND else base_qty

    if unit_cost is not None and unit is not None and unit.pk != product.base_unit_id:
        # El costo llega por presentación (p. ej. por rollo); se guarda por unidad base.
        unit_cost = (Decimal(unit_cost) * Decimal(quantity) / base_qty).quantize(COST_PLACES)

    try:
        return _apply(
            kind, product, warehouse, signed, user, unit_cost, reference,
            client_uuid, occurred_at, allow_negative,
        ), True
    except IntegrityError:
        # Dos reintentos simultáneos con el mismo client_uuid: el otro ganó.
        if client_uuid:
            return StockMovement.objects.get(client_uuid=client_uuid), False
        raise


def _apply(kind, product, warehouse, signed, user, unit_cost, reference,
           client_uuid, occurred_at, allow_negative):
    with transaction.atomic():
        level, _ = StockLevel.objects.select_for_update().get_or_create(
            product=product, warehouse=warehouse
        )
        if signed > 0:
            # Entra: con su costo (compra, o el original si es una devolución) o, si no trae, al
            # promedio vigente. Recalcula el promedio ponderado (spec 004, decisión 1).
            cost = Decimal(unit_cost) if unit_cost is not None else level.average_cost
            level.average_cost = next_average(level.quantity, level.average_cost, signed, cost)
        else:
            cost = level.average_cost  # sale al costo promedio de este momento
        new_balance = level.quantity + signed
        if new_balance < 0 and not allow_negative:
            raise InsufficientStock(
                f"Stock insuficiente de {product.sku} en {warehouse.code}: "
                f"hay {level.quantity}, se piden {-signed}."
            )
        level.quantity = new_balance
        level.save(update_fields=["quantity", "average_cost"])
        movement = StockMovement.objects.create(
            kind=kind,
            product=product,
            warehouse=warehouse,
            quantity=signed,
            unit_cost=cost,
            balance_after=new_balance,
            reference=reference,
            client_uuid=client_uuid,
            needs_review=new_balance < 0,
            user=user,
            occurred_at=occurred_at or timezone.now(),
        )
    return movement
