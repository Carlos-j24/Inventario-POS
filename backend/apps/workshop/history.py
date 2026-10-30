"""Historial de la moto y recordatorios como los muestra la API (spec 012, T3).

Funciones que arman diccionarios: las usan la ficha de la moto (api.py) y la lista de mantenimientos
(maintenance_api.py).
"""
from decimal import Decimal

from django.db.models import Prefetch

from .maintenance import due_of
from .models import MaintenanceReminder, WorkOrder, WorkOrderEvent, WorkOrderLine


def money(value):
    return f"{value:.2f}"


def _done(order):
    """Lo que se le hizo: lo cobrado (aprobado y no regresado)."""
    return [line for line in order.lines.all() if line.approved and line.returned_movement_id is None]


def order_history(order):
    delivered = order.status == WorkOrder.Status.DELIVERED
    done = _done(order) if delivered else []
    events = [e for e in order.events.all() if e.status == WorkOrder.Status.DELIVERED]
    return {
        "id": order.pk,
        "number": order.number,
        "status": order.status,
        "received_at": order.received_at,
        "delivered_at": events[-1].at if delivered and events else None,
        "mileage_in": order.mileage_in,
        "mileage_out": order.mileage_out,
        "request": order.request,
        "diagnosis": order.diagnosis,
        "mechanic": order.mechanic.get_full_name() or order.mechanic.username if order.mechanic else None,
        "lines": [
            {"sku": line.product.sku, "name": line.product.name, "is_service": line.is_service,
             "quantity": f"{line.quantity:.3f}", "total": money(line.total)}
            for line in done
        ],
        "total": money(sum((line.total for line in done), Decimal(0))) if delivered else None,
    }


def motorcycle_history(motorcycle):
    """Sus órdenes, de la más reciente a la más antigua; lo hecho solo en las entregadas (spec 012, regla 1)."""
    orders = motorcycle.work_orders.select_related("mechanic").prefetch_related(
        Prefetch("lines", queryset=WorkOrderLine.objects.select_related("product")),
        Prefetch("events", queryset=WorkOrderEvent.objects.order_by("at", "id")),
    ).order_by("-received_at", "-id")
    return [order_history(order) for order in orders]


def reminder_data(reminder, today=None):
    """Un recordatorio con cuándo vence; la fecha estimada solo en los abiertos."""
    open_ = reminder.status in MaintenanceReminder.OPEN
    due = due_of(reminder, today) if open_ else None
    return {
        "id": reminder.pk,
        "plan": {"id": reminder.plan_id, "name": reminder.plan.name},
        "status": reminder.status,
        "due_date": reminder.due_date,
        "due_mileage": reminder.due_mileage,
        "due_on": due.on if due else None,
        "by_km": due.by_km if due else False,
        "estimated": due.estimated if due else False,
        "daily_km": f"{due.usage:.1f}" if due and due.usage is not None else None,
        "note": reminder.note,
        "source_order": reminder.source_order.number,
        "done_order": reminder.done_order.number if reminder.done_order_id else None,
        "notices": [
            {"channel": n.channel, "user": n.user.username, "at": n.at} for n in reminder.notices.all()
        ],
        "closed_at": reminder.closed_at,
    }


def motorcycle_reminders(motorcycle, today=None):
    """Los recordatorios de la moto: los abiertos primero y luego los cerrados, los más recientes arriba."""
    rows = motorcycle.reminders.select_related("plan", "source_order", "done_order", "motorcycle").prefetch_related(
        "notices__user", "motorcycle__mileage_readings",
    ).order_by("-created_at", "-id")
    rows = sorted(rows, key=lambda r: r.status not in MaintenanceReminder.OPEN)
    return [reminder_data(r, today) for r in rows]
