"""Órdenes de trabajo (spec 011, T2 y T3): de que la moto entra a que sale.

Reglas:
- Recepción (`workshop.receive`) recibe, asigna, pone el precio de la mano de obra, registra la
  aprobación y cancela. El mecánico (`workshop.repair`) solo trabaja en las órdenes que tiene
  asignadas: diagnóstico, repuestos y mano de obra (sin precio), sacar y regresar repuestos, y "lista".
- Lo agregado queda por aprobar; solo lo aprobado sale de la bodega y se cobra (regla 4). El precio
  de lo aprobado ya no cambia.
- Los repuestos salen de la bodega principal al sacarlos para la moto y, si no se usan o la orden
  se cancela, vuelven a ella al costo con que salieron (decisión 1).
- Lista, recepción la manda a la caja como un pedido del día (spec 002) con lo aprobado a sus precios;
  la caja lo cobra sin sacar otra vez los repuestos. Solo cobrada se entrega (reglas 8 y 9).
- Cada cambio de estado queda en WorkOrderEvent con quién y cuándo.
"""
import uuid
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.inventory.models import StockMovement, Warehouse
from apps.inventory.services import record_movement
from apps.sales.models import Order, Sale, business_date
from apps.sales.orders import create_order

from .models import WorkOrder, WorkOrderApproval, WorkOrderEvent, WorkOrderLine
from .services import update_mileage

Status = WorkOrder.Status
RECEIVE, REPAIR = "workshop.receive", "workshop.repair"
EDITABLE = (Status.RECEIVED, Status.AWAITING_APPROVAL, Status.IN_REPAIR)  # aún se le agregan o quitan cosas


def is_reception(user):
    return user.has_app_permission(RECEIVE)


def _require_reception(user):
    if not is_reception(user):
        raise PermissionDenied("Esto lo hace recepción del taller.")


def _require_worker(order, user):
    """Recepción, o el mecánico asignado a esta orden."""
    if is_reception(user):
        return
    if not user.has_app_permission(REPAIR) or order.mechanic_id != user.pk:
        raise PermissionDenied(f"La orden {order.number} no está asignada a ti.")


def _lock(order):
    return WorkOrder.objects.select_for_update().select_related("motorcycle").get(pk=order.pk)


def _require_status(order, allowed, action):
    if order.status not in allowed:
        raise ValidationError(f"La orden {order.number} está {order.get_status_display().lower()}: no se puede {action}.")


def _set_status(order, status, user, note=""):
    order.status = status
    order.save(update_fields=["status", "updated_at"])
    WorkOrderEvent.objects.create(work_order=order, status=status, user=user, note=note)


def _check_mechanic(mechanic):
    if mechanic is None:
        return
    if not mechanic.has_app_permission(REPAIR):  # un usuario inactivo no tiene permisos
        raise ValidationError({"mechanic": f"{mechanic.username} no es un mecánico activo."})


@transaction.atomic
def receive_order(*, user, motorcycle, mileage, request, condition="", mechanic=None, mileage_note=""):
    """Recibe la moto: actualiza su kilometraje y abre la orden. Devuelve la orden."""
    _require_reception(user)
    if not motorcycle.is_active:
        raise ValidationError("La moto está inactiva: reactívala antes de recibirla.")
    if WorkOrder.objects.filter(motorcycle=motorcycle, status__in=WorkOrder.OPEN).exists():
        raise ValidationError("La moto ya tiene una orden de trabajo abierta.")
    if not request.strip():
        raise ValidationError({"request": "Escribe lo que pide el cliente."})
    _check_mechanic(mechanic)
    if mileage != motorcycle.mileage:
        motorcycle = update_mileage(motorcycle=motorcycle, mileage=mileage, user=user, note=mileage_note)
    order = WorkOrder.objects.create(
        motorcycle=motorcycle, customer=motorcycle.owner, mileage_in=mileage, request=request.strip(),
        condition=condition.strip(), mechanic=mechanic, received_by=user,
    )
    WorkOrderEvent.objects.create(work_order=order, status=Status.RECEIVED, user=user)
    return order


@transaction.atomic
def assign_mechanic(*, order, mechanic, user):
    _require_reception(user)
    order = _lock(order)
    _require_status(order, WorkOrder.OPEN, "cambiar el mecánico")
    _check_mechanic(mechanic)
    order.mechanic = mechanic
    order.save(update_fields=["mechanic", "updated_at"])
    return order


@transaction.atomic
def diagnose(*, order, user, diagnosis):
    order = _lock(order)
    _require_worker(order, user)
    _require_status(order, EDITABLE, "cambiar el diagnóstico")
    order.diagnosis = diagnosis.strip()
    order.save(update_fields=["diagnosis", "updated_at"])
    return order


@transaction.atomic
def add_line(*, order, user, product, quantity, unit_price=None):
    """Agrega un repuesto (al precio del catálogo) o mano de obra. Queda por aprobar."""
    order = _lock(order)
    _require_worker(order, user)
    _require_status(order, EDITABLE, "agregar repuestos ni mano de obra")
    if not product.is_active:  # uno pendiente de precio siempre está inactivo (spec 006)
        raise ValidationError({"product": f"{product.sku} no está a la venta."})
    quantity = Decimal(quantity)
    if quantity <= 0:
        raise ValidationError({"quantity": "La cantidad debe ser positiva."})
    if not product.is_service and not product.allows_fractions and quantity != quantity.to_integral_value():
        raise ValidationError({"quantity": f"{product.sku} no se vende fraccionado."})
    price = product.sale_price
    if unit_price is not None:
        if not product.is_service:
            raise ValidationError({"unit_price": "Los repuestos van al precio del catálogo."})
        _require_reception(user)  # el mecánico no pone precios
        price = _price(unit_price)
    return WorkOrderLine.objects.create(
        work_order=order, product=product, is_service=product.is_service, quantity=quantity, unit_price=price, added_by=user,
    )


def _price(value):
    price = Decimal(value)
    if price < 0:
        raise ValidationError({"unit_price": "El precio no puede ser negativo."})
    return price


def _lock_line(line):
    line = WorkOrderLine.objects.select_for_update().select_related("product").get(pk=line.pk)
    return line, _lock(line.work_order)


@transaction.atomic
def set_price(*, line, user, unit_price):
    """Recepción pone el precio de la mano de obra antes de que el cliente la apruebe."""
    _require_reception(user)
    line, order = _lock_line(line)
    _require_status(order, EDITABLE, "cambiar precios")
    if not line.is_service:
        raise ValidationError({"unit_price": "Los repuestos van al precio del catálogo."})
    if line.approved:
        raise ValidationError({"unit_price": "El cliente ya aprobó ese precio: no cambia."})
    line.unit_price = _price(unit_price)
    line.save(update_fields=["unit_price"])
    return line


@transaction.atomic
def remove_line(*, line, user):
    """Quita algo que no salió de la bodega (por aprobar, o aprobado pero que al final no se usó)."""
    line, order = _lock_line(line)
    _require_worker(order, user)
    _require_status(order, EDITABLE, "quitar repuestos ni mano de obra")
    if line.movement_id:
        raise ValidationError("Ese repuesto ya salió de la bodega: regrésalo en vez de quitarlo.")
    line.delete()


def pending_lines(order):
    return order.lines.filter(approved=False)


def charged_lines(order):
    """Lo que el cliente ha aprobado y sigue en la orden (sin lo regresado a la bodega)."""
    return order.lines.filter(approved=True, returned_movement__isnull=True)


def charged_total(order):
    return sum((line.total for line in charged_lines(order)), Decimal(0))


def paid_sale(order):
    """La venta que cobró la orden, si no se anuló."""
    return Sale.objects.filter(order__work_order=order, status=Sale.Status.COMPLETED).first()


def till_order(order):
    """El pedido de hoy que espera en la caja, si hay uno."""
    return order.sales_orders.filter(status=Order.Status.PENDING, business_date=business_date()).first()


@transaction.atomic
def send_for_approval(*, order, user):
    """El presupuesto está listo para mostrárselo al cliente."""
    order = _lock(order)
    _require_worker(order, user)
    _require_status(order, (Status.RECEIVED, Status.IN_REPAIR), "pedir aprobación")
    if not pending_lines(order).exists():
        raise ValidationError("No hay nada por aprobar: agrega repuestos o mano de obra.")
    _set_status(order, Status.AWAITING_APPROVAL, user)
    return order


@transaction.atomic
def approve(*, order, user, approved_by, channel):
    """El cliente aprobó lo pendiente: se puede sacar de la bodega y se cobrará. La orden pasa a reparación."""
    _require_reception(user)
    order = _lock(order)
    _require_status(order, EDITABLE, "registrar la aprobación")
    if not approved_by.strip():
        raise ValidationError({"approved_by": "Escribe quién aprobó."})
    if channel not in WorkOrderApproval.Channel.values:
        raise ValidationError({"channel": "Elige cómo aprobó: en persona o por llamada."})
    pending = pending_lines(order)
    if not pending.exists():
        raise ValidationError("No hay nada por aprobar.")
    free = pending.filter(is_service=True, unit_price=0).select_related("product").first()
    if free:
        raise ValidationError(f"Ponle precio a {free.product.name} antes de aprobar.")
    pending.update(approved=True)
    WorkOrderApproval.objects.create(
        work_order=order, approved_by=approved_by.strip(), channel=channel, total=charged_total(order), recorded_by=user,
    )
    _set_status(order, Status.IN_REPAIR, user, note=f"Aprobó {approved_by.strip()}")
    return order


def _main_warehouse():
    warehouse = Warehouse.objects.filter(is_default=True, is_active=True).first()
    if warehouse is None:
        raise ValidationError("No hay bodega principal: márcala en el admin.")
    return warehouse


@transaction.atomic
def take_part(*, line, user):
    """El repuesto aprobado sale de la bodega principal para la moto."""
    line, order = _lock_line(line)
    _require_worker(order, user)
    _require_status(order, (Status.IN_REPAIR,), "sacar repuestos")
    if line.is_service:
        raise ValidationError("La mano de obra no sale de la bodega.")
    if not line.approved:
        raise ValidationError("El cliente todavía no aprueba ese repuesto.")
    if line.movement_id:
        raise ValidationError("Ese repuesto ya salió de la bodega.")
    line.movement, _ = record_movement(
        kind=StockMovement.Kind.WORKSHOP_OUT, product=line.product, warehouse=_main_warehouse(), quantity=line.quantity,
        user=user, reference=f"Orden {order.number}",
    )
    line.save(update_fields=["movement"])
    return line


def _bring_back(line, order, user):
    line.returned_movement, _ = record_movement(
        kind=StockMovement.Kind.WORKSHOP_RETURN, product=line.product, warehouse=line.movement.warehouse,
        quantity=line.quantity, user=user, reference=f"Orden {order.number}",
        unit_cost=line.movement.unit_cost,  # vuelve al costo con que salió
    )
    line.save(update_fields=["returned_movement"])


@transaction.atomic
def return_part(*, line, user):
    """El repuesto no se usó: vuelve a la bodega y no se cobra."""
    line, order = _lock_line(line)
    _require_worker(order, user)
    _require_status(order, EDITABLE, "regresar repuestos")
    if not line.movement_id:
        raise ValidationError("Ese repuesto no ha salido de la bodega.")
    if line.returned_movement_id:
        raise ValidationError("Ese repuesto ya volvió a la bodega.")
    _bring_back(line, order, user)
    return line


@transaction.atomic
def mark_ready(*, order, user):
    """El trabajo terminó: todo lo aprobado está puesto y no queda nada por aprobar."""
    order = _lock(order)
    _require_worker(order, user)
    _require_status(order, (Status.IN_REPAIR,), "marcar lista")
    if pending_lines(order).exists():
        raise ValidationError("Hay cambios sin aprobar: que el cliente los apruebe o quítalos.")
    untaken = order.lines.filter(approved=True, is_service=False, movement__isnull=True).select_related("product").first()
    if untaken:
        raise ValidationError(f"{untaken.product.name} está aprobado pero no ha salido de la bodega: sácalo o quítalo.")
    _set_status(order, Status.READY, user)
    return order


@transaction.atomic
def send_to_till(*, order, user):
    """La orden lista va a la caja como un pedido del día, con lo aprobado a sus precios. Devuelve el pedido."""
    _require_reception(user)
    order = _lock(order)
    _require_status(order, (Status.READY,), "mandar a la caja")
    if paid_sale(order):
        raise ValidationError(f"La orden {order.number} ya está cobrada.")
    waiting = till_order(order)
    if waiting:
        raise ValidationError(f"La orden {order.number} ya está en la caja: pedido {waiting.code}.")
    lines = [
        {"product": line.product, "quantity": line.quantity, "unit_price": line.unit_price, "work_order_line": line}
        for line in charged_lines(order).select_related("product__base_unit")
    ]
    if not lines:
        raise ValidationError("No hay nada que cobrar: agrega la mano de obra o cancela la orden.")
    sales_order, _ = create_order(user=user, lines=lines, client_uuid=uuid.uuid4(), work_order=order)
    WorkOrderEvent.objects.create(work_order=order, status=order.status, user=user, note=f"A la caja: pedido {sales_order.code}")
    return sales_order


@transaction.atomic
def deliver(*, order, user, mileage=None, mileage_note=""):
    """Entrega la moto cobrada. El kilometraje de salida actualiza el de la moto si cambió."""
    _require_reception(user)
    order = _lock(order)
    _require_status(order, (Status.READY,), "entregar")
    if not paid_sale(order):
        raise ValidationError(f"La orden {order.number} no está cobrada: mándala a la caja.")
    motorcycle = order.motorcycle
    if mileage is not None and mileage != motorcycle.mileage:
        motorcycle = update_mileage(motorcycle=motorcycle, mileage=mileage, user=user, note=mileage_note)
    order.mileage_out = motorcycle.mileage
    order.save(update_fields=["mileage_out", "updated_at"])
    _set_status(order, Status.DELIVERED, user)
    return order


@transaction.atomic
def cancel(*, order, user, reason):
    """Cancela la orden: lo que salió de la bodega y no ha vuelto, vuelve, y su pedido sale de la caja."""
    _require_reception(user)
    order = _lock(order)
    _require_status(order, WorkOrder.OPEN, "cancelar")
    if not reason.strip():
        raise ValidationError({"reason": "Escribe por qué se cancela."})
    sale = paid_sale(order)
    if sale:
        raise ValidationError(f"La orden {order.number} ya está cobrada: anula la venta {sale.number} primero.")
    order.sales_orders.filter(status=Order.Status.PENDING).update(
        status=Order.Status.CANCELLED, cancelled_by=user, cancelled_at=timezone.now(),
    )
    # Sin select_for_update: la orden ya está bloqueada y el lado opcional de un join no se bloquea en PostgreSQL.
    taken = order.lines.filter(movement__isnull=False, returned_movement__isnull=True)
    for line in taken.select_related("product", "movement__warehouse"):
        _bring_back(line, order, user)
    _set_status(order, Status.CANCELLED, user, note=reason.strip()[:200])
    return order
