from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import F, Q

from apps.cash.models import CashRegister


def two_years_after(day):
    """Vigencia máxima de una autorización de numeración (Res. DIAN 165 de 2023, art. 48)."""
    try:
        return day.replace(year=day.year + 2)
    except ValueError:  # 29 de febrero
        return day.replace(year=day.year + 2, day=28)


class NumberingResolution(models.Model):
    """Autorización de numeración de la DIAN para una caja (spec 005, T2).

    Cada caja tiene la suya por tipo de documento, con su propio prefijo (art. 43). El siguiente
    número se toma con bloqueo dentro de la transacción del documento: sin huecos ni repetidos.
    """

    class DocumentType(models.TextChoices):
        POS = "POS", "Documento equivalente POS"
        INVOICE = "INVOICE", "Factura electrónica"
        CONTINGENCY = "CONTINGENCY", "Contingencia"

    register = models.ForeignKey(CashRegister, on_delete=models.PROTECT, related_name="resolutions", verbose_name="caja")
    document_type = models.CharField("tipo de documento", max_length=12, choices=DocumentType.choices)
    number = models.CharField("número de la resolución", max_length=30)
    issued_on = models.DateField("fecha de la resolución")
    valid_from = models.DateField("vigente desde")
    valid_until = models.DateField("vigente hasta")
    prefix = models.CharField(
        "prefijo", max_length=4, blank=True,
        validators=[RegexValidator(r"^[A-Z0-9]*$", "Hasta 4 letras mayúsculas o dígitos.")],
    )
    range_from = models.PositiveBigIntegerField("desde el número")
    range_to = models.PositiveBigIntegerField("hasta el número")
    next_number = models.PositiveBigIntegerField("siguiente número", help_text="Lo lleva el sistema.")
    is_active = models.BooleanField("activa", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["register", "document_type", "valid_from", "range_from"]
        verbose_name = "resolución de numeración"
        verbose_name_plural = "resoluciones de numeración"
        constraints = [
            models.CheckConstraint(condition=Q(range_from__gte=1) & Q(range_to__gte=F("range_from")), name="numbering_valid_range"),
            models.CheckConstraint(
                condition=Q(next_number__gte=F("range_from")) & Q(next_number__lte=F("range_to") + 1),
                name="numbering_next_in_range",
            ),
            models.CheckConstraint(
                condition=Q(valid_from__gte=F("issued_on")) & Q(valid_until__gte=F("valid_from")),
                name="numbering_valid_dates",
            ),
        ]

    def __str__(self):
        return f"{self.register.code} · {self.get_document_type_display()} · {self.prefix}{self.range_from}–{self.prefix}{self.range_to}"

    @property
    def remaining(self):
        return self.range_to - self.next_number + 1

    def format(self, number):
        """Prefijo y consecutivo, sin ceros a la izquierda (art. 43)."""
        return f"{self.prefix}{number}"

    def save(self, *args, **kwargs):
        if self.next_number is None:
            self.next_number = self.range_from
        super().save(*args, **kwargs)

    def clean(self):
        errors = {}
        if self.issued_on and self.valid_until and self.valid_until > two_years_after(self.issued_on):
            errors["valid_until"] = "La DIAN autoriza la numeración por máximo dos años desde la resolución."
        if self.range_from and self.range_to and self.range_to < self.range_from:
            errors["range_to"] = "El rango termina antes de empezar."
        elif self.range_from and self.range_to:
            # Un mismo prefijo no puede repetir números para el mismo tipo de documento, en ninguna caja.
            overlapping = NumberingResolution.objects.filter(
                document_type=self.document_type, prefix=self.prefix,
                range_from__lte=self.range_to, range_to__gte=self.range_from,
            ).exclude(pk=self.pk)
            if overlapping.exists():
                errors["range_from"] = f"El rango se cruza con otra resolución del prefijo «{self.prefix}»."
        if errors:
            raise ValidationError(errors)
