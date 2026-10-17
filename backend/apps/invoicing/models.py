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
            # Contingencia y POS generan el mismo documento (DE-POS): sus números no pueden cruzarse.
            same_document = SHARED_NUMBERING.get(self.document_type, {self.document_type})
            overlapping = NumberingResolution.objects.filter(
                document_type__in=same_document, prefix=self.prefix,
                range_from__lte=self.range_to, range_to__gte=self.range_from,
            ).exclude(pk=self.pk)
            if overlapping.exists():
                errors["range_from"] = f"El rango se cruza con otra resolución del prefijo «{self.prefix}»."
        if errors:
            raise ValidationError(errors)


SHARED_NUMBERING = {
    NumberingResolution.DocumentType.POS: {NumberingResolution.DocumentType.POS, NumberingResolution.DocumentType.CONTINGENCY},
    NumberingResolution.DocumentType.CONTINGENCY: {NumberingResolution.DocumentType.POS, NumberingResolution.DocumentType.CONTINGENCY},
}


class ContingencyBlock(models.Model):
    """Números de contingencia reservados por un equipo de caja para vender sin servidor (T5)."""

    register = models.ForeignKey(CashRegister, on_delete=models.PROTECT, related_name="contingency_blocks", verbose_name="caja")
    resolution = models.ForeignKey(NumberingResolution, on_delete=models.PROTECT, related_name="blocks", verbose_name="resolución")
    start = models.PositiveBigIntegerField("desde")
    end = models.PositiveBigIntegerField("hasta")
    reserved_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+", verbose_name="reservó")
    reserved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-reserved_at"]
        verbose_name = "bloque de contingencia"
        verbose_name_plural = "bloques de contingencia"

    def __str__(self):
        return f"{self.register.code} · {self.resolution.prefix}{self.start}–{self.resolution.prefix}{self.end}"


class FiscalDocument(models.Model):
    """Documento electrónico de una venta, anulación o devolución (spec 005, T3).

    El DE-POS y la factura llevan numeración autorizada de la caja; las notas, un consecutivo
    interno (art. 22 y 36). Nace pendiente: la cola de envío (T4) lo manda al proveedor.
    """

    class Kind(models.TextChoices):
        POS = "POS", "Documento equivalente POS"
        INVOICE = "INVOICE", "Factura electrónica"
        POS_ADJUSTMENT = "POS_ADJUSTMENT", "Nota de ajuste"
        CREDIT_NOTE = "CREDIT_NOTE", "Nota crédito"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pendiente de envío"
        VALIDATED = "VALIDATED", "Validado por la DIAN"
        REJECTED = "REJECTED", "Rechazado"

    kind = models.CharField("tipo", max_length=16, choices=Kind.choices)
    status = models.CharField("estado", max_length=10, choices=Status.choices, default=Status.PENDING)
    sale = models.ForeignKey("sales.Sale", on_delete=models.PROTECT, related_name="fiscal_documents", verbose_name="venta")
    sale_return = models.ForeignKey(
        "sales.SaleReturn", on_delete=models.PROTECT, related_name="fiscal_documents", null=True, blank=True,
        verbose_name="devolución",
    )
    corrects = models.ForeignKey(
        "self", on_delete=models.PROTECT, related_name="notes", null=True, blank=True,
        verbose_name="documento que corrige",
    )
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, related_name="fiscal_documents", verbose_name="cliente")
    resolution = models.ForeignKey(
        NumberingResolution, on_delete=models.PROTECT, related_name="documents", null=True, blank=True,
        verbose_name="resolución",
    )
    prefix = models.CharField("prefijo", max_length=4, blank=True)
    number = models.PositiveBigIntegerField("número")
    issued_at = models.DateTimeField("generado")
    subtotal = models.DecimalField(max_digits=14, decimal_places=2)
    tax = models.DecimalField(max_digits=14, decimal_places=2)
    total = models.DecimalField(max_digits=14, decimal_places=2)
    cude = models.CharField("CUFE/CUDE", max_length=96, blank=True)
    qr_data = models.TextField("contenido del QR", blank=True)
    provider_id = models.CharField("id en el proveedor", max_length=80, blank=True)
    attempts = models.PositiveIntegerField("intentos de envío", default=0)
    last_error = models.TextField("último error", blank=True)
    validated_at = models.DateTimeField("validado", null=True, blank=True)
    contingency = models.BooleanField(
        "contingencia", default=False, help_text="Venta sin conexión: el tiquete se entregó antes de transmitir (art. 37).",
    )
    created_at = models.DateTimeField("recibido", auto_now_add=True, null=True)
    next_attempt_at = models.DateTimeField(
        "próximo intento", null=True, blank=True, db_index=True, help_text="La cola espera hasta entonces tras una falla.",
    )

    class Meta:
        ordering = ["-issued_at", "-pk"]
        verbose_name = "documento electrónico"
        verbose_name_plural = "documentos electrónicos"
        constraints = [
            models.UniqueConstraint(fields=["kind", "prefix", "number"], name="unique_fiscal_number"),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} {self.code}"

    @property
    def code(self):
        return f"{self.prefix}{self.number}"

    @property
    def is_note(self):
        return self.kind in (self.Kind.POS_ADJUSTMENT, self.Kind.CREDIT_NOTE)


class FiscalEvent(models.Model):
    """Historial de un documento: creación, envíos, validación, rechazos y errores."""

    document = models.ForeignKey(FiscalDocument, on_delete=models.CASCADE, related_name="events")
    at = models.DateTimeField(auto_now_add=True)
    kind = models.CharField(max_length=20)
    detail = models.TextField(blank=True)

    class Meta:
        ordering = ["at", "pk"]


class InternalCounter(models.Model):
    """Consecutivo interno (las notas no usan numeración autorizada de la DIAN)."""

    key = models.CharField(max_length=30, unique=True)
    next_number = models.PositiveBigIntegerField(default=1)
