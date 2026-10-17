from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

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
    # seller cobró la venta (cajero); salesperson la vendió (quien armó el pedido, o el cajero si fue directa).
    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="sales", verbose_name="cobró (cajero)"
    )
    salesperson = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="sales_made", verbose_name="vendió"
    )
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
    # Revisión de ventas marcadas (needs_review): la marca se conserva, esto dice quién la atendió.
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+", null=True, blank=True
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.CharField(max_length=200, blank=True)

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
    vat_excluded = models.BooleanField(default=False, help_text="Copiado del producto al vender (spec 005).")
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


def business_date(moment=None):
    """Fecha de negocio en la zona horaria de la tienda (America/Bogota): los pedidos vencen al cambiar."""
    return timezone.localdate(moment)


class Order(models.Model):
    """Pedido que arma un vendedor y cobra la caja (spec 002). No mueve inventario: eso pasa al cobrar."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pendiente"
        PAID = "PAID", "Pagado"
        CANCELLED = "CANCELLED", "Cancelado"
        EXPIRED = "EXPIRED", "Vencido"

    # Código de 4 dígitos para dictarlo en el mostrador; único entre los pedidos del mismo día.
    code = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1000), MaxValueValidator(9999)]
    )
    business_date = models.DateField(default=business_date)
    client_uuid = models.UUIDField(unique=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    salesperson = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders")
    total = models.DecimalField(**MONEY, help_text="Suma de las líneas, IVA incluido.")
    created_at = models.DateTimeField(auto_now_add=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+", null=True, blank=True
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    sale = models.OneToOneField(Sale, on_delete=models.PROTECT, related_name="order", null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["business_date", "code"], name="unique_order_code_per_day"),
            models.CheckConstraint(
                condition=Q(code__gte=1000, code__lte=9999), name="order_code_four_digits"
            ),
            # Un pedido pagado siempre tiene su venta, y solo uno pagado la tiene.
            models.CheckConstraint(
                condition=Q(status="PAID", sale__isnull=False) | (~Q(status="PAID") & Q(sale__isnull=True)),
                name="order_paid_iff_sale",
            ),
        ]
        verbose_name = "pedido"

    def effective_status(self, today=None):
        """Un pedido pendiente de un día anterior ya está vencido, aunque nadie haya cambiado su estado."""
        if self.status == self.Status.PENDING and self.business_date < (today or business_date()):
            return self.Status.EXPIRED
        return self.status

    def __str__(self):
        return f"Pedido {self.code} ({self.business_date:%Y-%m-%d}) · {self.total}"


class OrderLine(models.Model):
    """Línea del pedido con el precio congelado: es lo que el vendedor le dijo al cliente."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="+")
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="+")
    quantity = models.DecimalField(**QTY, validators=[MinValueValidator(Decimal("0.001"))])
    unit_price = models.DecimalField(**MONEY, help_text="Precio por unidad pedida, IVA incluido.")
    total = models.DecimalField(**MONEY)

    class Meta:
        verbose_name = "línea de pedido"
        verbose_name_plural = "líneas de pedido"
