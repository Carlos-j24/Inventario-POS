"""Registro de ventas: la venta, sus líneas, la salida de inventario y los pagos van en una sola transacción."""
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.cash.models import Shift
from apps.cash.services import apply_payments
from apps.catalog.models import ProductUnit
from apps.inventory.models import StockMovement
from apps.inventory.services import record_movement

from .models import Sale, SaleLine

CENT = Decimal("0.01")


def money(value):
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def catalog_price(product, unit):
    """Precio del catálogo en la unidad vendida: precio base × factor de la presentación."""
    if unit.pk == product.base_unit_id:
        return product.sale_price
    try:
        factor = product.units.get(unit=unit).factor
    except ProductUnit.DoesNotExist:
        raise ValidationError(f"{product.sku} no se maneja en la unidad '{unit}'.")
    return money(product.sale_price * factor)


def split_tax(total, rate):
    """Separa el IVA de un valor que ya lo incluye."""
    subtotal = money(total / (1 + rate / 100))
    return subtotal, total - subtotal


def create_sale(*, user, shift, lines, payments, client_uuid, offline=False, occurred_at=None):
    """Registra y cobra una venta en el turno de una caja. Devuelve (venta, creada).

    lines: dicts con product, quantity y opcionalmente unit y unit_price.
    payments: dicts con method y amount (ver cash.services.apply_payments).
    En línea se cobra el precio del catálogo, no se vende sin stock y el turno debe estar abierto.
    Sin conexión se respeta el precio que cobró el POS, se acepta stock negativo y un turno
    ya cerrado; si algo de eso pasa, la venta queda marcada para revisión.
    """
    existing = Sale.objects.filter(client_uuid=client_uuid).first()
    if existing:
        return existing, False
    if not lines:
        raise ValidationError("La venta no tiene líneas.")
    try:
        sale = _create(user, shift, lines, payments, client_uuid, offline, occurred_at or timezone.now())
        return sale, True
    except IntegrityError:
        # Dos envíos simultáneos de la misma venta: el otro ganó.
        existing = Sale.objects.filter(client_uuid=client_uuid).first()
        if existing is None:
            raise
        return existing, False


def _create(user, shift, lines, payments, client_uuid, offline, occurred_at):
    with transaction.atomic():
        # Bloquear el turno evita que se cierre a mitad de una venta.
        shift = Shift.objects.select_for_update().select_related("register").get(pk=shift.pk)
        late = shift.status != Shift.Status.OPEN
        if late and not offline:
            raise ValidationError("El turno está cerrado: abre un turno nuevo para vender.")
        warehouse = shift.register.warehouse
        sale = Sale.objects.create(
            client_uuid=client_uuid, shift=shift, warehouse=warehouse, seller=user, salesperson=user,
            offline=offline,
            subtotal=0, tax=0, total=0, occurred_at=occurred_at,
        )
        review = late
        for line in lines:
            product = line["product"]
            unit = line.get("unit") or product.base_unit
            quantity = Decimal(line["quantity"])
            if quantity <= 0:
                raise ValidationError("Las cantidades deben ser positivas.")
            listed = catalog_price(product, unit)
            charged = listed
            if offline and line.get("unit_price") is not None:
                charged = money(line["unit_price"])
            total = money(charged * quantity)
            rate = Decimal(product.tax_rate)
            subtotal, tax = split_tax(total, rate)
            movement, _ = record_movement(
                kind=StockMovement.Kind.SALE, product=product, warehouse=warehouse,
                quantity=quantity, unit=unit, user=user, reference=f"Venta {client_uuid}",
                occurred_at=occurred_at, allow_negative=offline,
            )
            SaleLine.objects.create(
                sale=sale, product=product, unit=unit, quantity=quantity,
                unit_price=charged, catalog_price=listed, tax_rate=rate,
                subtotal=subtotal, tax=tax, total=total, movement=movement,
            )
            review = review or movement.needs_review or charged != listed
            sale.subtotal += subtotal
            sale.tax += tax
            sale.total += total
        sale.needs_review = review
        sale.save(update_fields=["subtotal", "tax", "total", "needs_review"])
        apply_payments(sale=sale, shift=shift, payments=payments)
        StockMovement.objects.filter(sale_line__sale=sale).update(reference=f"Venta {sale.number}")
    return sale
