from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.catalog.models import MONEY
from apps.inventory.models import Warehouse


class CashRegister(models.Model):
    """Caja física (Caja 1, Caja 2). Vende de la bodega a la que pertenece."""

    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=60)
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="registers")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]
        verbose_name = "caja"

    def __str__(self):
        return f"{self.code} · {self.name}"


class Shift(models.Model):
    """Turno de una caja: se abre con una base y se cierra contando el efectivo."""

    class Status(models.TextChoices):
        OPEN = "OPEN", "Abierto"
        CLOSED = "CLOSED", "Cerrado"

    register = models.ForeignKey(CashRegister, on_delete=models.PROTECT, related_name="shifts")
    status = models.CharField(max_length=6, choices=Status.choices, default=Status.OPEN)
    opened_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    opened_at = models.DateTimeField(auto_now_add=True)
    opening_float = models.DecimalField(**MONEY, help_text="Base en efectivo al abrir.")
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+", null=True, blank=True
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    expected_cash = models.DecimalField(**MONEY, null=True, blank=True)
    counted_cash = models.DecimalField(**MONEY, null=True, blank=True)
    difference = models.DecimalField(
        **MONEY, null=True, blank=True, help_text="Contado − esperado: negativo es faltante."
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-opened_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["register"], condition=Q(status="OPEN"), name="one_open_shift_per_register"
            )
        ]
        verbose_name = "turno"

    def __str__(self):
        return f"{self.register.code} · {self.opened_at:%Y-%m-%d %H:%M} · {self.get_status_display()}"


class Payment(models.Model):
    class Method(models.TextChoices):
        CASH = "CASH", "Efectivo"
        CARD = "CARD", "Tarjeta"
        TRANSFER = "TRANSFER", "Transferencia"

    sale = models.ForeignKey("sales.Sale", on_delete=models.PROTECT, related_name="payments")
    shift = models.ForeignKey(Shift, on_delete=models.PROTECT, related_name="payments")
    method = models.CharField(max_length=10, choices=Method.choices)
    amount = models.DecimalField(**MONEY, help_text="Lo que se abona a la venta.")
    received = models.DecimalField(**MONEY, help_text="Lo que entregó el cliente (efectivo).")
    change = models.DecimalField(**MONEY, default=0, help_text="Vueltas entregadas.")
    reference = models.CharField(max_length=60, blank=True, help_text="Voucher o número de transferencia.")

    class Meta:
        verbose_name = "pago"

    def __str__(self):
        return f"{self.get_method_display()} {self.amount}"
