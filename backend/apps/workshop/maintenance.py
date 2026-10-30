"""Historial y recordatorios de mantenimiento (spec 012, T2).

Reglas:
- Al entregar una orden (spec 011) que se cobró con productos de un plan, se cierra como hecho el
  recordatorio abierto de esa moto y ese plan, y se crea el siguiente: fecha de entrega + días del plan
  y kilometraje de salida + km del plan (regla 3). Un plan inactivo no crea nuevos.
- Entre visitas, el kilometraje se estima con el uso diario de las lecturas (regla 4).
- Un recordatorio vence en la primera fecha entre la del plan y la estimada por km. Aparece en la
  lista desde 7 días antes, y vence ya si una lectura pasó sus km (regla 5).
- Recepción (`workshop.receive`) avisa, ajusta y descarta (reglas 6 y 9).
"""
import math
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from .models import MaintenanceNotice, MaintenancePlan, MaintenanceReminder

Status = MaintenanceReminder.Status
RECEIVE = "workshop.receive"
WINDOW_DAYS = 7         # aparece en la lista desde una semana antes
USAGE_DAYS = 365        # lecturas que cuentan para el uso diario
MIN_SPAN_DAYS = 14      # con menos días entre la primera y la última lectura no se estima


# --- estimación (funciones puras) ------------------------------------------------------------------

def daily_usage(readings, today):
    """Km al día según las lecturas [(fecha, km, km anterior)] en orden de toma, o None si no alcanza.

    Cuentan los últimos 12 meses. Si el kilometraje bajó (cambio de tablero, con su nota), la cuenta
    empieza en esa lectura: las de antes son de otro tablero.
    """
    recent = [r for r in readings if r[0] >= today - timedelta(days=USAGE_DAYS)]
    start = 0
    for i, (_, mileage, previous) in enumerate(recent):
        if previous is not None and mileage < previous:
            start = i
    recent = recent[start:]
    if len(recent) < 2:
        return None
    (first_day, first_km, _), (last_day, last_km, _) = recent[0], recent[-1]
    days = (last_day - first_day).days
    if days < MIN_SPAN_DAYS:
        return None
    usage = Decimal(last_km - first_km) / days
    return usage if usage > 0 else None


def km_due_date(due_mileage, last_day, last_mileage, usage):
    """Cuándo llega la moto a `due_mileage`: el día de la lectura si ya pasó, o estimado con el uso."""
    if due_mileage is None:
        return None
    if last_mileage >= due_mileage:
        return last_day
    if usage is None:
        return None
    return last_day + timedelta(days=math.ceil((due_mileage - last_mileage) / usage))


@dataclass(frozen=True)
class Due:
    """Cuándo vence un recordatorio y por qué."""

    on: date | None
    by_km: bool = False          # vence primero por kilometraje
    estimated: bool = False      # ese kilometraje es estimado ("aprox."), no leído
    km_on: date | None = None    # la fecha en que llega a los km, leída o estimada
    usage: Decimal | None = None


def due_of(reminder, today=None):
    """Cuándo vence el recordatorio, con las lecturas de su moto (traerlas con prefetch en listas)."""
    today = today or timezone.localdate()
    moto = reminder.motorcycle
    readings = sorted(moto.mileage_readings.all(), key=lambda r: (r.recorded_at, r.pk))
    usage = daily_usage([(timezone.localdate(r.recorded_at), r.mileage, r.previous) for r in readings], today)
    last_day = timezone.localdate(moto.mileage_at) if moto.mileage_at else today
    km_on = km_due_date(reminder.due_mileage, last_day, moto.mileage, usage)
    dates = [d for d in (reminder.due_date, km_on) if d is not None]
    if not dates:
        return Due(on=None, usage=usage)
    on = min(dates)
    by_km = km_on is not None and km_on == on and (reminder.due_date is None or km_on < reminder.due_date)
    reached = reminder.due_mileage is not None and moto.mileage >= reminder.due_mileage
    return Due(on=on, by_km=by_km, estimated=by_km and not reached, km_on=km_on, usage=usage)


def due_reminders(*, today=None, plan=None, include_notified=False):
    """Los recordatorios abiertos que vencen en la próxima semana o ya vencieron, los vencidos primero."""
    today = today or timezone.localdate()
    statuses = [Status.PENDING, Status.NOTIFIED] if include_notified else [Status.PENDING]
    rows = MaintenanceReminder.objects.filter(status__in=statuses).select_related(
        "plan", "motorcycle__owner", "source_order", "done_order",
    ).prefetch_related("motorcycle__mileage_readings", "notices__user")
    if plan is not None:
        rows = rows.filter(plan=plan)
    limit = today + timedelta(days=WINDOW_DAYS)
    due = [(reminder, due_of(reminder, today)) for reminder in rows]
    due = [(reminder, d) for reminder, d in due if d.on is not None and d.on <= limit]
    return sorted(due, key=lambda item: (item[1].on, item[0].pk))


# --- al entregar ----------------------------------------------------------------------------------

def on_delivered(*, order, user):
    """Cierra los recordatorios que cumplió la orden y crea los siguientes. Lo llama la entrega."""
    products = order.lines.filter(approved=True, returned_movement__isnull=True).values_list("product", flat=True)
    plans = MaintenancePlan.objects.filter(products__in=products).distinct()
    today, now = timezone.localdate(), timezone.now()
    created = []
    for plan in plans:
        due = {
            "due_date": today + timedelta(days=plan.every_days) if plan.every_days else None,
            "due_mileage": order.mileage_out + plan.every_km if plan.every_km else None,
        }
        current = MaintenanceReminder.objects.select_for_update().filter(
            motorcycle=order.motorcycle, plan=plan, status__in=MaintenanceReminder.OPEN,
        ).first()
        if current is not None and current.source_order_id == order.pk:
            # Se entrega otra vez después de anular su venta (spec 011): se recalcula el mismo.
            if plan.is_active:
                MaintenanceReminder.objects.filter(pk=current.pk).update(**due, updated_at=now)
            continue
        if current is not None:
            current.status, current.done_order = Status.DONE, order
            current.closed_by, current.closed_at = user, now
            current.save(update_fields=["status", "done_order", "closed_by", "closed_at", "updated_at"])
        if plan.is_active:
            created.append(MaintenanceReminder.objects.create(
                motorcycle=order.motorcycle, plan=plan, source_order=order, **due,
            ))
    return created


# --- recepción: avisar, ajustar y descartar --------------------------------------------------------

def _require_reception(user):
    if not user.has_app_permission(RECEIVE):
        raise PermissionDenied("Esto lo hace recepción del taller.")


def _lock_open(reminder, action):
    reminder = MaintenanceReminder.objects.select_for_update().select_related("plan").get(pk=reminder.pk)
    if reminder.status not in MaintenanceReminder.OPEN:
        raise ValidationError(f"El recordatorio está {reminder.get_status_display().lower()}: no se puede {action}.")
    return reminder


@transaction.atomic
def notify(*, reminder, user, channel):
    """Recepción le avisó al cliente (por WhatsApp o llamada). Sigue abierto hasta hacerse o descartarse."""
    _require_reception(user)
    reminder = _lock_open(reminder, "avisar")
    if channel not in MaintenanceNotice.Channel.values:
        raise ValidationError({"channel": "Elige cómo avisó: WhatsApp o llamada."})
    MaintenanceNotice.objects.create(reminder=reminder, channel=channel, user=user)
    reminder.status = Status.NOTIFIED
    reminder.save(update_fields=["status", "updated_at"])
    return reminder


@transaction.atomic
def adjust(*, reminder, user, due_date=None, due_mileage=None, note):
    """Cambia cuándo vence, por ejemplo si el cliente dijo que viene más adelante."""
    _require_reception(user)
    reminder = _lock_open(reminder, "ajustar")
    if due_date is None and due_mileage is None:
        raise ValidationError("Pon una fecha, un kilometraje o los dos.")
    if due_mileage is not None and due_mileage <= 0:
        raise ValidationError({"due_mileage": "El kilometraje debe ser mayor que cero."})
    if not note.strip():
        raise ValidationError({"note": "Escribe por qué se ajusta."})
    reminder.due_date, reminder.due_mileage, reminder.note = due_date, due_mileage, note.strip()[:200]
    reminder.save(update_fields=["due_date", "due_mileage", "note", "updated_at"])
    return reminder


@transaction.atomic
def dismiss(*, reminder, user, note):
    """No se va a hacer (la moto se vendió, el cliente no quiere el aviso). Sale de la lista."""
    _require_reception(user)
    reminder = _lock_open(reminder, "descartar")
    if not note.strip():
        raise ValidationError({"note": "Escribe por qué se descarta."})
    reminder.status, reminder.note = Status.DISMISSED, note.strip()[:200]
    reminder.closed_by, reminder.closed_at = user, timezone.now()
    reminder.save(update_fields=["status", "note", "closed_by", "closed_at", "updated_at"])
    return reminder
