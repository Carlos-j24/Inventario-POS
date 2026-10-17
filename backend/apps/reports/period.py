"""Período de un reporte: ?from=AAAA-MM-DD&to=AAAA-MM-DD, en fechas de negocio (hora de Bogotá)."""
import datetime

from rest_framework.exceptions import ValidationError

from apps.sales.models import business_date

MAX_DAYS = 366


def parse_period(params):
    """Devuelve (desde, hasta). Por defecto, hoy (decisión 2 de la spec 004)."""
    today = business_date()
    try:
        start = datetime.date.fromisoformat(params["from"]) if params.get("from") else today
        end = datetime.date.fromisoformat(params["to"]) if params.get("to") else start
    except ValueError:
        raise ValidationError({"period": "Usa fechas con el formato AAAA-MM-DD."})
    if start > end:
        raise ValidationError({"period": "La fecha inicial no puede ser posterior a la final."})
    if (end - start).days >= MAX_DAYS:
        raise ValidationError({"period": "El período puede tener como máximo un año."})
    return start, end
