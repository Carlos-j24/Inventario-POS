"""Pedidos (spec 002): el vendedor arma, la caja cobra.

- Crear: congela el precio del catálogo en cada línea y asigna un código de 4 dígitos libre ese día.
- Cancelar: el propio vendedor, o quien tenga sales.void. Solo pedidos pendientes de hoy.
- Vencer: los pendientes de días anteriores. Order.effective_status ya los trata como vencidos;
  expire_orders deja el estado guardado al día (para listados y reportes).
El pedido no mueve inventario: el stock baja al cobrarlo (T3).
"""
import secrets
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from apps.catalog.units import to_base_quantity
from apps.inventory.models import StockLevel

from .models import Order, OrderLine, business_date
from .services import catalog_price, money

CODE_ATTEMPTS = 20


def _random_code():
    return 1000 + secrets.randbelow(9000)


def create_order(*, user, lines, client_uuid):
    """Crea un pedido pendiente y devuelve (pedido, creado). Reenviar el mismo client_uuid no lo duplica.

    lines: dicts con product, quantity y opcionalmente unit (la base si falta).
    """
    existing = Order.objects.filter(client_uuid=client_uuid).first()
    if existing:
        return existing, False
    if not lines:
        raise ValidationError("El pedido no tiene líneas.")

    priced = []
    for line in lines:
        product = line["product"]
        unit = line.get("unit") or product.base_unit
        quantity = Decimal(line["quantity"])
        if quantity <= 0:
            raise ValidationError("Las cantidades deben ser positivas.")
        to_base_quantity(product, quantity, unit)  # valida la unidad y las fracciones
        price = catalog_price(product, unit)
        priced.append((product, unit, quantity, price, money(price * quantity)))
    total = sum((p[4] for p in priced), Decimal(0))

    # El código es aleatorio para que no se adivine el siguiente; si choca con otro del día, se reintenta.
    for _ in range(CODE_ATTEMPTS):
        try:
            with transaction.atomic():
                order = Order.objects.create(
                    code=_random_code(), client_uuid=client_uuid, salesperson=user, total=total,
                )
                OrderLine.objects.bulk_create(
                    OrderLine(order=order, product=p, unit=u, quantity=q, unit_price=price, total=t)
                    for p, u, q, price, t in priced
                )
            return order, True
        except IntegrityError:
            existing = Order.objects.filter(client_uuid=client_uuid).first()
            if existing:  # dos envíos simultáneos del mismo pedido
                return existing, False
            # si no, chocó el código del día: se intenta con otro
    raise ValidationError("No hay códigos de pedido libres; intenta de nuevo.")


def cancel_order(*, order, user):
    """Cancela un pedido pendiente de hoy. Uno ajeno exige el permiso sales.void."""
    if order.salesperson_id != user.pk and not user.has_app_permission("sales.void"):
        raise PermissionDenied("Solo quien hizo el pedido o un supervisor puede cancelarlo.")
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order.pk)
        status = order.effective_status()
        if status != Order.Status.PENDING:
            raise ValidationError(f"El pedido {order.code} está {Order.Status(status).label.lower()}.")
        order.status = Order.Status.CANCELLED
        order.cancelled_by = user
        order.cancelled_at = timezone.now()
        order.save(update_fields=["status", "cancelled_by", "cancelled_at"])
    return order


def expire_orders(today=None):
    """Marca como vencidos los pedidos pendientes de días anteriores. Devuelve cuántos."""
    return Order.objects.filter(
        status=Order.Status.PENDING, business_date__lt=today or business_date()
    ).update(status=Order.Status.EXPIRED)


def stock_warnings(order):
    """Avisos para el vendedor (decisión 4: solo avisar, no bloquear).

    Compara lo pedido con el stock total en unidad base. Devuelve una lista de
    dicts: sku, name, kind ("sin_existencias" o "bajo_minimo"), available.
    """
    needed = {}
    for line in order.lines.select_related("product", "unit"):
        base = to_base_quantity(line.product, line.quantity, line.unit)
        needed[line.product] = needed.get(line.product, Decimal(0)) + base
    warnings = []
    for product, qty in needed.items():
        available = StockLevel.objects.filter(product=product).aggregate(q=Sum("quantity"))["q"] or Decimal(0)
        if available < qty:
            kind = "sin_existencias"
        elif available - qty < product.min_stock:
            kind = "bajo_minimo"
        else:
            continue
        warnings.append({"sku": product.sku, "name": product.name, "kind": kind, "available": available})
    return warnings
