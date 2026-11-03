"""Gastos del negocio (spec 013, regla 7): lo que sale para arriendo, sueldos, servicios o insumos.

Un gasto no se borra: se corrige o se anula, y cada cambio queda en ExpenseEvent. Si se pagó con la
plata del cajón, va ligado al turno abierto y el arqueo lo descuenta (decisión 7).
"""
from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.catalog.models import MONEY


class ExpenseCategory(models.Model):
    """Lista corta que edita el administrador. Una categoría con gastos no se borra: se desactiva."""

    name = models.CharField("nombre", max_length=60, unique=True)
    is_active = models.BooleanField("activa", default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "categoría de gasto"
        verbose_name_plural = "categorías de gasto"

    def __str__(self):
        return self.name


class Expense(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Vigente"
        VOIDED = "VOIDED", "Anulado"

    spent_on = models.DateField("fecha")
    amount = models.DecimalField("valor", **MONEY)
    category = models.ForeignKey(ExpenseCategory, on_delete=models.PROTECT, related_name="expenses", verbose_name="categoría")
    note = models.CharField("nota", max_length=200, blank=True)
    # Pagado con el efectivo del cajón: sale del arqueo de ese turno.
    shift = models.ForeignKey(
        "cash.Shift", on_delete=models.PROTECT, related_name="expenses", null=True, blank=True,
        verbose_name="pagado de la caja (turno)",
    )
    status = models.CharField(max_length=6, choices=Status.choices, default=Status.ACTIVE)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    void_reason = models.CharField(max_length=200, blank=True)
    voided_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+", null=True, blank=True)
    voided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-spent_on", "-pk"]
        verbose_name = "gasto"
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0), name="expense_amount_positive",
                violation_error_message="El valor del gasto debe ser positivo.",
            ),
        ]

    def __str__(self):
        return f"{self.spent_on} · {self.category} · {self.amount}"


class ExpenseEvent(models.Model):
    """Rastro del gasto: quién lo anotó, lo corrigió o lo anuló, y qué cambió."""

    class Kind(models.TextChoices):
        CREATED = "CREATED", "Anotado"
        CHANGED = "CHANGED", "Corregido"
        VOIDED = "VOIDED", "Anulado"

    expense = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name="events")
    kind = models.CharField(max_length=7, choices=Kind.choices)
    detail = models.CharField(max_length=300, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["at", "pk"]
