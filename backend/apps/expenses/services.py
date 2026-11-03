"""Gastos (spec 013, T5).

Reglas:
- Valor positivo, fecha que no sea futura y categoría activa.
- "Pagado de la caja": va al turno abierto de esa caja, con la fecha de hoy, y el arqueo lo descuenta.
  Con el turno ya cerrado, su valor no cambia ni se anula: el arqueo ya lo contó.
- Nunca se borra: se corrige o se anula con motivo, y cada cambio queda en ExpenseEvent.
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.cash.models import Shift

from .models import Expense, ExpenseEvent

Status = Expense.Status
Kind = ExpenseEvent.Kind


def _money(value):
    return "$" + f"{Decimal(value):,.0f}".replace(",", ".")


def _check(spent_on, amount, category):
    if Decimal(amount) <= 0:
        raise ValidationError({"amount": "El valor del gasto debe ser positivo."})
    if spent_on > timezone.localdate():
        raise ValidationError({"spent_on": "La fecha del gasto no puede ser futura."})
    if not category.is_active:
        raise ValidationError({"category": f"La categoría {category.name} está desactivada."})


def _open_shift(register):
    shift = Shift.objects.select_for_update().filter(register=register, status=Shift.Status.OPEN).first()
    if shift is None:
        raise ValidationError({"register": f"{register.name} no tiene un turno abierto: el gasto no puede salir de su cajón."})
    return shift


@transaction.atomic
def create_expense(*, user, spent_on, amount, category, note="", register=None):
    """Anota un gasto. Con `register`, se pagó del cajón de esa caja (su turno abierto, hoy)."""
    _check(spent_on, amount, category)
    shift = None
    if register is not None:
        if spent_on != timezone.localdate():
            raise ValidationError({"spent_on": "Lo que sale de la caja es de hoy: el arqueo de otro día ya se cerró."})
        shift = _open_shift(register)
    expense = Expense.objects.create(
        spent_on=spent_on, amount=amount, category=category, note=note.strip(), shift=shift, created_by=user,
    )
    detail = f"{_money(amount)} en {category.name}" + (f", pagado de {shift.register.name}" if shift else "")
    ExpenseEvent.objects.create(expense=expense, kind=Kind.CREATED, detail=detail, user=user)
    return expense


def _lock(expense):
    expense = Expense.objects.select_for_update().get(pk=expense.pk)
    if expense.status != Status.ACTIVE:
        raise ValidationError("El gasto está anulado: ya no se corrige.")
    return expense


def _till_closed(expense):
    return expense.shift_id is not None and expense.shift.status != Shift.Status.OPEN


@transaction.atomic
def update_expense(*, user, expense, **changes):
    """Corrige fecha, valor, categoría o nota, dejando qué cambió."""
    expense = _lock(expense)
    spent_on = changes.get("spent_on", expense.spent_on)
    amount = Decimal(changes.get("amount", expense.amount))
    category = changes.get("category", expense.category)
    note = changes.get("note", expense.note).strip()
    _check(spent_on, amount, category)
    if expense.shift_id and spent_on != expense.spent_on:
        raise ValidationError({"spent_on": "Lo que salió de la caja queda con la fecha de su turno."})
    if _till_closed(expense) and amount != expense.amount:
        raise ValidationError({"amount": "El turno de la caja ya cerró: su arqueo contó este valor."})
    diffs = []
    if spent_on != expense.spent_on:
        diffs.append(f"fecha {expense.spent_on:%Y-%m-%d} → {spent_on:%Y-%m-%d}")
    if amount != expense.amount:
        diffs.append(f"valor {_money(expense.amount)} → {_money(amount)}")
    if category != expense.category:
        diffs.append(f"categoría {expense.category.name} → {category.name}")
    if note != expense.note:
        diffs.append(f"nota «{expense.note}» → «{note}»")
    if not diffs:
        return expense
    expense.spent_on, expense.amount, expense.category, expense.note = spent_on, amount, category, note
    expense.save(update_fields=["spent_on", "amount", "category", "note"])
    ExpenseEvent.objects.create(expense=expense, kind=Kind.CHANGED, detail="; ".join(diffs)[:300], user=user)
    return expense


@transaction.atomic
def void_expense(*, user, expense, reason):
    """Anula el gasto con su motivo: deja de contar en el resumen y, si salió de la caja, en el arqueo."""
    expense = _lock(expense)
    if not reason.strip():
        raise ValidationError({"reason": "Escribe por qué se anula."})
    if _till_closed(expense):
        raise ValidationError("El turno de la caja ya cerró: su arqueo contó este gasto.")
    expense.status = Status.VOIDED
    expense.void_reason = reason.strip()[:200]
    expense.voided_by = user
    expense.voided_at = timezone.now()
    expense.save(update_fields=["status", "void_reason", "voided_by", "voided_at"])
    ExpenseEvent.objects.create(expense=expense, kind=Kind.VOIDED, detail=expense.void_reason, user=user)
    return expense


def till_expenses(shift):
    """Lo que salió del cajón del turno por gastos vigentes."""
    return shift.expenses.filter(status=Status.ACTIVE).aggregate(t=Sum("amount"))["t"] or Decimal(0)
