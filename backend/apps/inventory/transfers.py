"""Traslados entre bodegas (spec 006, T7).

Reglas:
- Lo hace quien tiene inventory.transfer (decisión 5), de una bodega activa a otra distinta.
- Un solo paso (decisión 4): todas las salidas (TRANSFER_OUT) y entradas (TRANSFER_IN) se registran
  en una transacción; entran todas o ninguna.
- Sale al costo promedio del origen y entra al destino con ese mismo costo, así el inventario
  valorizado total no cambia por mover mercancía.
- No puede dejar en negativo el origen.
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.catalog.units import to_base_quantity

from .models import StockMovement, Transfer, TransferLine
from .services import record_movement

Kind = StockMovement.Kind


def _lines(origin, destination, lines):
    """Valida el traslado y deja cada línea en unidad base."""
    if origin.pk == destination.pk:
        raise ValidationError("El origen y el destino deben ser bodegas distintas.")
    for warehouse in (origin, destination):
        if not warehouse.is_active:
            raise ValidationError(f"La bodega {warehouse.code} está inactiva.")
    if not lines:
        raise ValidationError("El traslado no tiene líneas.")
    built = []
    for item in lines:
        product, quantity = item["product"], Decimal(item["quantity"])
        unit = item.get("unit") or product.base_unit
        if quantity <= 0:
            raise ValidationError(f"{product.sku}: la cantidad debe ser mayor que cero.")
        built.append((product, unit, quantity, to_base_quantity(product, quantity, unit)))
    return built


def create_transfer(*, user, client_uuid, origin, destination, lines, note=""):
    """Registra el traslado ya aplicado. Devuelve (traslado, creado); con el mismo client_uuid, el que ya existe."""
    existing = Transfer.objects.filter(client_uuid=client_uuid).first()
    if existing:
        return existing, False
    built = _lines(origin, destination, lines)
    try:
        with transaction.atomic():
            transfer = Transfer.objects.create(
                client_uuid=client_uuid, origin=origin, destination=destination,
                note=(note or "").strip()[:200], created_by=user,
            )
            reference = f"{transfer.number} {origin.code} a {destination.code}"
            for product, unit, quantity, base in built:
                out, _ = record_movement(
                    kind=Kind.TRANSFER_OUT, product=product, warehouse=origin, quantity=base,
                    user=user, reference=reference,
                )
                # Entra con el costo con que salió: el promedio del origen en ese momento.
                inbound, _ = record_movement(
                    kind=Kind.TRANSFER_IN, product=product, warehouse=destination, quantity=base,
                    unit_cost=out.unit_cost, user=user, reference=reference,
                )
                TransferLine.objects.create(
                    transfer=transfer, product=product, unit=unit, quantity=quantity, base_quantity=base,
                    out_movement=out, in_movement=inbound,
                )
    except IntegrityError:
        # Dos envíos simultáneos con el mismo client_uuid: el otro ganó.
        return Transfer.objects.get(client_uuid=client_uuid), False
    return transfer, True
