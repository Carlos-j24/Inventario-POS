import uuid

from django.conf import settings
from django.db import models

from apps.catalog.models import MONEY, QTY, Product


class Warehouse(models.Model):
    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=80)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]
        verbose_name = "bodega"

    def __str__(self):
        return f"{self.code} · {self.name}"


class StockMovement(models.Model):
    """Línea del kardex. Nunca se edita ni se borra: los errores se corrigen con otro movimiento."""

    class Kind(models.TextChoices):
        RECEIPT = "RECEIPT", "Entrada (compra)"
        SALE = "SALE", "Venta"
        RETURN = "RETURN", "Devolución de cliente"
        ADJUSTMENT = "ADJUSTMENT", "Ajuste"
        TRANSFER_OUT = "TRANSFER_OUT", "Traslado (salida)"
        TRANSFER_IN = "TRANSFER_IN", "Traslado (entrada)"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # UUID que genera el cliente: si el POS reenvía una venta hecha sin conexión, no se duplica.
    client_uuid = models.UUIDField(unique=True, null=True, blank=True)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="movements")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="movements")
    quantity = models.DecimalField(**QTY, help_text="En unidad base; positiva entra, negativa sale.")
    unit_cost = models.DecimalField(**MONEY, null=True, blank=True)
    balance_after = models.DecimalField(**QTY)
    reference = models.CharField(max_length=80, blank=True)
    needs_review = models.BooleanField(
        default=False, help_text="Dejó el stock en negativo (p. ej. venta sincronizada sin conexión)."
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    occurred_at = models.DateTimeField(help_text="Cuándo pasó (puede ser antes de sincronizar).")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["product", "warehouse", "created_at"])]
        verbose_name = "movimiento de inventario"
        verbose_name_plural = "movimientos de inventario"

    def __str__(self):
        return f"{self.get_kind_display()} {self.quantity} {self.product.sku}"


class StockLevel(models.Model):
    """Saldo actual por producto y bodega. Solo lo actualiza services.record_movement."""

    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="stock_levels")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="stock_levels")
    quantity = models.DecimalField(**QTY, default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["product", "warehouse"], name="unique_stock_level")
        ]
        verbose_name = "existencia"

    def __str__(self):
        return f"{self.product.sku} @ {self.warehouse.code}: {self.quantity}"
