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

from .models import Order, Sale, SaleLine

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


def create_sale(*, user, shift, lines, payments, client_uuid, offline=False, occurred_at=None, order=None):
    """Registra y cobra una venta en el turno de una caja. Devuelve (venta, creada).

    lines: dicts con product, quantity y opcionalmente unit y unit_price.
    payments: dicts con method y amount (ver cash.services.apply_payments).
    En línea se cobra el precio del catálogo, no se vende sin stock y el turno debe estar abierto.
    Sin conexión se respeta el precio que cobró el POS, se acepta stock negativo y un turno
    ya cerrado; si algo de eso pasa, la venta queda marcada para revisión.

    Con order (spec 002) se cobra un pedido: lines son dicts con order_line y quantity (o None
    para cobrarlo completo), se cobra el precio del pedido y la venta queda a nombre de su vendedor.
    """
    existing = Sale.objects.filter(client_uuid=client_uuid).first()
    if existing:
        return existing, False
    if order is not None and offline:
        raise ValidationError("Los pedidos se cobran con conexión.")
    if not lines and order is None:
        raise ValidationError("La venta no tiene líneas.")
    try:
        sale = _create(user, shift, lines, payments, client_uuid, offline, occurred_at or timezone.now(), order)
        return sale, True
    except IntegrityError:
        # Dos envíos simultáneos de la misma venta: el otro ganó.
        existing = Sale.objects.filter(client_uuid=client_uuid).first()
        if existing is None:
            raise
        return existing, False


def _order_lines(order, lines):
    """Líneas a cobrar de un pedido: todas, o un subconjunto sin pasar de lo pedido."""
    by_id = {line.pk: line for line in order.lines.select_related("product", "unit")}
    if lines is None:
        chosen = [(line, line.quantity) for line in by_id.values()]
    else:
        used = {}
        for item in lines:
            line = by_id.get(getattr(item["order_line"], "pk", item["order_line"]))
            if line is None:
                raise ValidationError("La línea no pertenece a este pedido.")
            quantity = Decimal(item["quantity"])
            if quantity <= 0:
                raise ValidationError("Las cantidades deben ser positivas.")
            used[line.pk] = used.get(line.pk, Decimal(0)) + quantity
            if used[line.pk] > line.quantity:
                raise ValidationError(f"{line.product.sku}: se pidieron {line.quantity}; no se puede cobrar más.")
        chosen = [(by_id[pk], quantity) for pk, quantity in used.items()]
    if not chosen:
        raise ValidationError("No hay nada que cobrar del pedido.")
    return [
        {"product": line.product, "unit": line.unit, "quantity": quantity, "agreed_price": line.unit_price}
        for line, quantity in chosen
    ]


def _lock_payable_order(order):
    order = Order.objects.select_for_update().get(pk=order.pk)
    status = order.effective_status()
    if status == Order.Status.PAID:
        raise ValidationError(f"El pedido {order.code} ya fue cobrado (venta {order.sale.number}).")
    if status != Order.Status.PENDING:
        raise ValidationError(f"El pedido {order.code} está {Order.Status(status).label.lower()}.")
    return order


def _create(user, shift, lines, payments, client_uuid, offline, occurred_at, order=None):
    with transaction.atomic():
        # Bloquear el turno evita que se cierre a mitad de una venta.
        shift = Shift.objects.select_for_update().select_related("register").get(pk=shift.pk)
        late = shift.status != Shift.Status.OPEN
        if late and not offline:
            raise ValidationError("El turno está cerrado: abre un turno nuevo para vender.")
        salesperson = user
        if order is not None:
            # Bloquear el pedido: dos cajas no pueden cobrarlo a la vez.
            order = _lock_payable_order(order)
            lines = _order_lines(order, lines)
            salesperson = order.salesperson
        warehouse = shift.register.warehouse
        sale = Sale.objects.create(
            client_uuid=client_uuid, shift=shift, warehouse=warehouse, seller=user, salesperson=salesperson,
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
            if line.get("agreed_price") is not None:
                charged = line["agreed_price"]  # precio del pedido (spec 002, decisión 1)
            elif offline and line.get("unit_price") is not None:
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
        if order is not None:
            order.status = Order.Status.PAID
            order.sale = sale
            order.save(update_fields=["status", "sale"])
    return sale
