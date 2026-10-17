from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

QTY = {"max_digits": 14, "decimal_places": 3}
MONEY = {"max_digits": 14, "decimal_places": 2}


class Category(models.Model):
    name = models.CharField(max_length=80, unique=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "categoría"

    def __str__(self):
        return self.name


class Unit(models.Model):
    """Unidad de medida: und, m, kg, rollo, bulto, caja..."""

    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=40)

    class Meta:
        ordering = ["code"]
        verbose_name = "unidad"

    def __str__(self):
        return self.code


class Product(models.Model):
    class TaxRate(models.TextChoices):
        EXEMPT = "0", "Exento (0 %)"
        REDUCED = "5", "5 %"
        GENERAL = "19", "19 %"

    sku = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=160)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    # Todo el inventario se guarda en la unidad base (p. ej. metros para un cable).
    base_unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="+")
    barcode = models.CharField(max_length=40, unique=True, null=True, blank=True)
    sale_price = models.DecimalField(**MONEY, validators=[MinValueValidator(0)])
    tax_rate = models.CharField(max_length=2, choices=TaxRate.choices, default=TaxRate.GENERAL)
    # Para la DIAN no es lo mismo exento (gravado al 0 %) que excluido (no causa IVA), aunque
    # ninguno cobre IVA (spec 005, T1). Solo tiene sentido con tarifa 0 %.
    vat_excluded = models.BooleanField(
        "excluido de IVA", default=False, help_text="No causa IVA (distinto de exento). Solo con tarifa 0 %."
    )
    allows_fractions = models.BooleanField(
        default=False, help_text="Se puede vender en cantidades no enteras (metros, kilos)."
    )
    min_stock = models.DecimalField(**QTY, default=0, validators=[MinValueValidator(0)])
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "producto"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(vat_excluded=False) | models.Q(tax_rate="0"),
                name="vat_excluded_only_at_zero_rate",
                violation_error_message="Un producto excluido de IVA debe tener tarifa 0 %%.",
            ),
        ]

    def __str__(self):
        return f"{self.sku} · {self.name}"


class ProductUnit(models.Model):
    """Presentación alternativa: 1 rollo = 100 m, 1 caja = 50 und."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="units")
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="+")
    factor = models.DecimalField(**QTY, validators=[MinValueValidator(Decimal("0.001"))])
    barcode = models.CharField(max_length=40, unique=True, null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["product", "unit"], name="unique_product_unit")]
        verbose_name = "presentación"
        verbose_name_plural = "presentaciones"

    def clean(self):
        if self.unit_id and self.unit_id == self.product.base_unit_id:
            raise ValidationError("La unidad base no necesita presentación: su factor siempre es 1.")

    def __str__(self):
        return f"{self.product.sku}: 1 {self.unit} = {self.factor} {self.product.base_unit}"
