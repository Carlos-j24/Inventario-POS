"""Consecutivos autorizados por la DIAN, por caja y tipo de documento (spec 005, T2)."""
import math

from django.db import transaction
from django.utils import timezone

from .models import NumberingResolution

# Avisos: quedan pocos números (el mayor entre 100 y el 10 % del rango) o faltan 30 días o menos.
LOW_NUMBERS = 100
LOW_FRACTION = 0.10
EXPIRY_WARNING_DAYS = 30


class NumberingError(Exception):
    """No hay numeración vigente: el documento no puede salir sin número autorizado."""


def take_numbers(register, document_type, count=1, today=None):
    """Toma los siguientes `count` números autorizados de una misma resolución. Devuelve
    (resolución, primero, último); si a la resolución le quedan menos, entrega los que tenga.

    Debe llamarse dentro de la transacción del documento: si esta se deshace, el número no se
    gasta. Se bloquean todas las resoluciones vigentes de la caja (no solo la primera) para que dos
    cajas no lean el mismo número ni se salten una resolución al agotarse la anterior. Si hay
    varias vigentes, se usa primero la más antigua.
    """
    today = today or timezone.localdate()
    with transaction.atomic():
        candidates = list(
            NumberingResolution.objects.select_for_update()
            .filter(register=register, document_type=document_type, is_active=True,
                    valid_from__lte=today, valid_until__gte=today)
            .order_by("valid_from", "range_from", "pk")
        )
        resolution = next((r for r in candidates if r.next_number <= r.range_to), None)
        if resolution is None:
            raise NumberingError(why_unavailable(register, document_type, today))
        first = resolution.next_number
        last = min(first + count - 1, resolution.range_to)
        resolution.next_number = last + 1
        resolution.save(update_fields=["next_number"])
    return resolution, first, last


def take_number(register, document_type, today=None):
    """Toma el siguiente número autorizado. Devuelve (resolución, número)."""
    resolution, number, _ = take_numbers(register, document_type, 1, today)
    return resolution, number


def why_unavailable(register, document_type, today):
    """Por qué no hay número: sin resolución, agotada, todavía no rige o vencida."""
    label = NumberingResolution.DocumentType(document_type).label
    resolutions = NumberingResolution.objects.filter(register=register, document_type=document_type, is_active=True)
    if not resolutions.exists():
        return f"La caja {register.code} no tiene resolución de numeración para {label}."
    if resolutions.filter(valid_from__lte=today, valid_until__gte=today).exists():
        return f"La numeración de {label} de la caja {register.code} se agotó: pide una resolución nueva a la DIAN."
    upcoming = resolutions.filter(valid_from__gt=today).order_by("valid_from").first()
    if upcoming:
        return f"La resolución {upcoming.number} de la caja {register.code} empieza a regir el {upcoming.valid_from:%d/%m/%Y}."
    last = resolutions.order_by("-valid_until").first()
    return f"La numeración de {label} de la caja {register.code} venció el {last.valid_until:%d/%m/%Y} (resolución {last.number})."


def resolution_status(resolution, today=None):
    """Estado y avisos de una resolución, para la caja y el administrador."""
    today = today or timezone.localdate()
    size = resolution.range_to - resolution.range_from + 1
    remaining = resolution.remaining
    days_left = (resolution.valid_until - today).days
    warnings = []
    if resolution.valid_from > today:
        state = "upcoming"
    elif days_left < 0:
        state = "expired"
        warnings.append(f"Venció el {resolution.valid_until:%d/%m/%Y}.")
    elif remaining <= 0:
        state = "exhausted"
        warnings.append("Se agotaron los números.")
    else:
        state = "current"
        if remaining <= max(LOW_NUMBERS, math.ceil(size * LOW_FRACTION)):
            warnings.append(f"Quedan {remaining} números.")
        if days_left <= EXPIRY_WARNING_DAYS:
            warnings.append("Vence hoy." if days_left == 0 else f"Vence en {days_left} días.")
    return {"state": state, "remaining": remaining, "days_left": days_left, "warnings": warnings}
