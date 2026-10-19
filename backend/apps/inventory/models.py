import uuid

from django.conf import settings
from django.db import models

from apps.catalog.models import QTY, Product

# Costos con 4 decimales: el costo por metro de un rollo no siempre da centavos exactos.
COST = {"max_digits": 16, "decimal_places": 4}


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
    # Costo por unidad base. Entradas: el de la compra. Salidas: el promedio ponderado del momento
    # (spec 004). Devoluciones: el mismo con que salió lo devuelto.
    unit_cost = models.DecimalField(**COST, null=True, blank=True)
    cost_estimated = models.BooleanField(
        default=False, help_text="Costo asignado después (ventas anteriores a la spec 004)."
    )
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
    average_cost = models.DecimalField(**COST, default=0, help_text="Costo promedio ponderado por unidad base.")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["product", "warehouse"], name="unique_stock_level")
        ]
        verbose_name = "existencia"

    def __str__(self):
        return f"{self.product.sku} @ {self.warehouse.code}: {self.quantity}"


class Adjustment(models.Model):
    """Ajuste de inventario (spec 006, T3): bajas por daño, pérdida o uso interno, y sobrantes.

    Lo pide bodega y lo aprueba quien tiene inventory.adjust (decisión 1). Aprobado o rechazado
    ya no cambia: un error se corrige con otro ajuste.
    """

    class Reason(models.TextChoices):  # lista fija (decisión 8)
        DAMAGE = "DAMAGE", "Daño"
        LOSS = "LOSS", "Pérdida o robo"
        INTERNAL_USE = "INTERNAL_USE", "Uso interno"
        EXPIRED = "EXPIRED", "Vencimiento o mal estado"
        RECORD_ERROR = "RECORD_ERROR", "Error de registro"
        SURPLUS = "SURPLUS", "Sobrante"
        PHYSICAL_COUNT = "PHYSICAL_COUNT", "Conteo físico"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pendiente de aprobación"
        APPROVED = "APPROVED", "Aprobado"
        REJECTED = "REJECTED", "Rechazado"

    client_uuid = models.UUIDField(unique=True, help_text="Un doble clic o un reintento no lo duplica.")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="adjustments", verbose_name="bodega")
    reason = models.CharField("motivo", max_length=16, choices=Reason.choices)
    note = models.TextField("nota")
    status = models.CharField("estado", max_length=10, choices=Status.choices, default=Status.PENDING)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+", verbose_name="pidió")
    created_at = models.DateTimeField(auto_now_add=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+", null=True, blank=True, verbose_name="decidió",
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    rejection_note = models.CharField("motivo del rechazo", max_length=200, blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "ajuste de inventario"
        verbose_name_plural = "ajustes de inventario"

    def __str__(self):
        return f"{self.number} · {self.get_reason_display()}"

    @property
    def number(self):
        return f"AJ-{self.pk:06d}"


class AdjustmentLine(models.Model):
    """Una línea del ajuste. La cantidad se guarda en unidad base, con signo: negativa sale."""

    adjustment = models.ForeignKey(Adjustment, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="+")
    unit = models.ForeignKey("catalog.Unit", on_delete=models.PROTECT, related_name="+", help_text="La que eligió quien lo pidió.")
    quantity = models.DecimalField(**QTY, help_text="En la unidad elegida, positiva.")
    base_quantity = models.DecimalField(**QTY, help_text="En unidad base, con signo: negativa sale, positiva entra.")
    unit_cost = models.DecimalField(
        **COST, null=True, blank=True, help_text="Por unidad base. Solo para sobrantes de un producto sin costo.",
    )
    movement = models.OneToOneField(
        StockMovement, on_delete=models.PROTECT, related_name="adjustment_line", null=True, blank=True,
    )

    class Meta:
        verbose_name = "línea de ajuste"
