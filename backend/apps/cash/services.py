"""Turnos de caja y pagos: abrir con base, cobrar con uno o varios medios, cerrar con arqueo."""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Sum
from django.utils import timezone

from .models import Payment, Shift

Method = Payment.Method


def open_shift(*, register, user, opening_float):
    if not register.is_active:
        raise ValidationError(f"La caja {register.code} está inactiva.")
    if Decimal(opening_float) < 0:
        raise ValidationError("La base no puede ser negativa.")
    try:
        with transaction.atomic():
            return Shift.objects.create(register=register, opened_by=user, opening_float=opening_float)
    except IntegrityError:
        raise ValidationError(f"La caja {register.code} ya tiene un turno abierto.")


def apply_payments(*, sale, shift, payments):
    """Registra los pagos de una venta. Se llama dentro de la transacción de la venta.

    payments: dicts con method, amount y opcionalmente reference. En efectivo, amount es
    lo que entregó el cliente; el sistema calcula las vueltas. Tarjeta y transferencia
    no pueden pasarse del total, porque no dan vueltas.
    """
    if not payments:
        raise ValidationError("La venta no tiene pagos.")
    non_cash = sum(Decimal(p["amount"]) for p in payments if p["method"] != Method.CASH)
    cash_received = sum(Decimal(p["amount"]) for p in payments if p["method"] == Method.CASH)
    if any(Decimal(p["amount"]) <= 0 for p in payments):
        raise ValidationError("Cada pago debe ser mayor que cero.")
    if non_cash > sale.total:
        raise ValidationError("Tarjeta y transferencia no pueden superar el total de la venta.")
    cash_due = sale.total - non_cash
    if cash_due == 0 and cash_received:
        raise ValidationError("La venta ya está cubierta sin efectivo: sobra el pago en efectivo.")
    if cash_received < cash_due:
        raise ValidationError(f"Falta dinero: el total es {sale.total} y se pagaron {non_cash + cash_received}.")

    for p in payments:
        if p["method"] != Method.CASH:
            Payment.objects.create(
                sale=sale, shift=shift, method=p["method"], amount=p["amount"],
                received=p["amount"], reference=p.get("reference", ""),
            )
    if cash_received:
        Payment.objects.create(
            sale=sale, shift=shift, method=Method.CASH, amount=cash_due,
            received=cash_received, change=cash_received - cash_due,
        )


def shift_summary(shift):
    """Totales del turno por medio de pago: cobros de ventas no anuladas menos reembolsos."""
    payments = shift.payments.filter(sale__status="COMPLETED")
    by_method = {m: Decimal(0) for m in Method.values}
    for row in payments.values("method").annotate(total=Sum("amount")):
        by_method[row["method"]] = row["total"]
    refunds = {m: Decimal(0) for m in Method.values}
    for row in shift.refunds.values("method").annotate(total=Sum("amount")):
        refunds[row["method"]] = row["total"]
    sales = payments.values("sale").distinct().aggregate(n=Count("sale"))["n"]
    return {
        "sales": sales,
        "by_method": by_method,
        "refunds": refunds,
        "expected_cash": shift.opening_float + by_method[Method.CASH] - refunds[Method.CASH],
    }


def close_shift(*, shift, user, counted_cash, notes=""):
    """Cierra el turno: guarda el efectivo esperado, el contado y la diferencia."""
    with transaction.atomic():
        shift = Shift.objects.select_for_update().get(pk=shift.pk)
        if shift.status != Shift.Status.OPEN:
            raise ValidationError("El turno ya está cerrado.")
        if Decimal(counted_cash) < 0:
            raise ValidationError("El efectivo contado no puede ser negativo.")
        expected = shift_summary(shift)["expected_cash"]
        shift.status = Shift.Status.CLOSED
        shift.closed_by = user
        shift.closed_at = timezone.now()
        shift.expected_cash = expected
        shift.counted_cash = counted_cash
        shift.difference = Decimal(counted_cash) - expected
        shift.notes = notes
        shift.save()
    return shift
