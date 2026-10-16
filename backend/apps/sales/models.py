from django.conf import settings
from django.db import models

from apps.catalog.models import MONEY, QTY, Product, Unit
from apps.inventory.models import StockMovement, Warehouse


class Sale(models.Model):
    class Status(models.TextChoices):
        COMPLETED = "COMPLETED", "Completada"
        VOIDED = "VOIDED", "Anulada"

    # UUID que genera el POS: reenviar la misma venta no la duplica.
    client_uuid = models.UUIDField(unique=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.COMPLETED)
    shift = models.ForeignKey("cash.Shift", on_delete=models.PROTECT, related_name="sales")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="sales")
    seller = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="sales")
    offline = models.BooleanField(default=False, help_text="Se hizo sin conexión y llegó al sincronizar.")
    needs_review = models.BooleanField(
        default=False,
        help_text="Dejó stock negativo, cobró un precio distinto al del catálogo o llegó con el turno cerrado.",
    )
    subtotal = models.DecimalField(**MONEY)
    tax = models.DecimalField(**MONEY)
    total = models.DecimalField(**MONEY)
    occurred_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+", null=True, blank=True
    )
    voided_at = models.DateTimeField(null=True, blank=True)
    void_reason = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "venta"

    @property
    def number(self):
        return f"V-{self.pk:06d}"

    def __str__(self):
        return f"{self.number} · {self.total}"


class SaleLine(models.Model):
    """Línea de venta. Los precios incluyen IVA (precio al público); el IVA se separa por línea."""

    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="+")
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="+")
    quantity = models.DecimalField(**QTY, help_text="En la unidad vendida.")
    unit_price = models.DecimalField(**MONEY, help_text="Precio por unidad vendida, IVA incluido.")
    catalog_price = models.DecimalField(**MONEY, help_text="Precio del catálogo al registrar la venta.")
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2)
    subtotal = models.DecimalField(**MONEY)
    tax = models.DecimalField(**MONEY)
    total = models.DecimalField(**MONEY)
    movement = models.OneToOneField(StockMovement, on_delete=models.PROTECT, related_name="sale_line")

    class Meta:
        verbose_name = "línea de venta"
        verbose_name_plural = "líneas de venta"

    def returned_quantity(self):
        return self.return_lines.aggregate(q=models.Sum("quantity"))["q"] or 0


class SaleReturn(models.Model):
    """Devolución parcial o total de una venta, con reembolso desde el turno abierto."""

    client_uuid = models.UUIDField(unique=True)
    sale = models.ForeignKey(Sale, on_delete=models.PROTECT, related_name="returns")
    shift = models.ForeignKey("cash.Shift", on_delete=models.PROTECT, related_name="returns")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    reason = models.CharField(max_length=200)
    total = models.DecimalField(**MONEY)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "devolución"
        verbose_name_plural = "devoluciones"

    @property
    def number(self):
        return f"D-{self.pk:06d}"

    def __str__(self):
        return f"{self.number} de {self.sale.number} · {self.total}"


class SaleReturnLine(models.Model):
    sale_return = models.ForeignKey(SaleReturn, on_delete=models.CASCADE, related_name="lines")
    sale_line = models.ForeignKey(SaleLine, on_delete=models.PROTECT, related_name="return_lines")
    quantity = models.DecimalField(**QTY, help_text="En la unidad en que se vendió.")
    subtotal = models.DecimalField(**MONEY)
    tax = models.DecimalField(**MONEY)
    total = models.DecimalField(**MONEY)
    movement = models.OneToOneField(StockMovement, on_delete=models.PROTECT, related_name="return_line")

    class Meta:
        verbose_name = "línea de devolución"
        verbose_name_plural = "líneas de devolución"
