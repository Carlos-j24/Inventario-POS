from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.customers.models import Customer

from .rules import clean_motorcycle, normalize_code


class Motorcycle(models.Model):
    """Una moto del taller (spec 009). No se borra: tendrá órdenes e historial."""

    plate = models.CharField("placa", max_length=8, blank=True, help_text="Sin espacios ni guiones, p. ej. ABC12D.")
    vin = models.CharField("número de chasis", max_length=20, blank=True, help_text="Obligatorio si no tiene placa.")
    brand = models.CharField("marca", max_length=60)
    model = models.CharField("modelo", max_length=80, blank=True, help_text="Línea o referencia, p. ej. Boxer CT 100.")
    year = models.PositiveSmallIntegerField("año", null=True, blank=True)
    displacement_cc = models.PositiveSmallIntegerField("cilindraje (cc)", null=True, blank=True)
    color = models.CharField("color", max_length=40, blank=True)
    mileage = models.PositiveIntegerField("kilometraje", default=0)
    mileage_at = models.DateTimeField("fecha del kilometraje", null=True, blank=True)
    notes = models.TextField("notas", blank=True)
    # El dueño actual; la historia completa está en Ownership. Solo lo cambia services.change_owner.
    owner = models.ForeignKey(Customer, verbose_name="dueño", on_delete=models.PROTECT, related_name="motorcycles")
    is_active = models.BooleanField("activa", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["plate", "vin"]
        verbose_name = "moto"
        constraints = [
            models.UniqueConstraint(
                fields=["plate"], condition=~Q(plate=""), name="unique_motorcycle_plate",
                violation_error_message="Ya existe una moto con esa placa.",
            ),
            models.UniqueConstraint(
                fields=["vin"], condition=~Q(vin=""), name="unique_motorcycle_vin",
                violation_error_message="Ya existe una moto con ese número de chasis.",
            ),
            models.CheckConstraint(condition=~Q(plate="") | ~Q(vin=""), name="motorcycle_plate_or_vin"),
        ]

    def __str__(self):
        name = " ".join(filter(None, [self.brand, self.model]))
        return f"{self.plate or f'Chasis {self.vin}'} · {name}"

    def clean_fields(self, exclude=None):
        # Antes de medir el largo: "X.Y.Z-12A" son 9 caracteres escritos pero una placa de 6.
        self.plate, self.vin = normalize_code(self.plate), normalize_code(self.vin)
        super().clean_fields(exclude=exclude)

    def clean(self):
        data = clean_motorcycle({
            "plate": self.plate, "vin": self.vin, "brand": self.brand, "model": self.model, "year": self.year,
        })
        self.plate, self.vin, self.brand, self.model = data["plate"], data["vin"], data["brand"], data["model"]
        # Repetidas, con el error en su campo: la restricción de la base, con condición, lo daría sin campo.
        # Django ya no revisa las restricciones de un campo que falló aquí.
        others = Motorcycle.objects.exclude(pk=self.pk)
        errors = {}
        if self.plate and others.filter(plate=self.plate).exists():
            errors["plate"] = "Ya existe una moto con esa placa."
        if self.vin and others.filter(vin=self.vin).exists():
            errors["vin"] = "Ya existe una moto con ese número de chasis."
        if errors:
            raise ValidationError(errors)


class Ownership(models.Model):
    """Quién fue dueño de la moto y desde cuándo. El abierto (sin `ended_at`) es el dueño actual."""

    motorcycle = models.ForeignKey(Motorcycle, on_delete=models.PROTECT, related_name="ownerships")
    customer = models.ForeignKey(Customer, verbose_name="dueño", on_delete=models.PROTECT, related_name="ownerships")
    started_at = models.DateTimeField("desde")
    ended_at = models.DateTimeField("hasta", null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")

    class Meta:
        ordering = ["-started_at", "-id"]
        verbose_name = "dueño de la moto"
        verbose_name_plural = "dueños de la moto"
        constraints = [
            models.UniqueConstraint(
                fields=["motorcycle"], condition=Q(ended_at__isnull=True), name="one_current_owner",
            ),
        ]

    def __str__(self):
        return f"{self.customer.name} ({self.motorcycle})"


class MileageReading(models.Model):
    """Cada lectura del kilometraje. Una que baja lleva su nota (spec 009, regla 5)."""

    motorcycle = models.ForeignKey(Motorcycle, on_delete=models.PROTECT, related_name="mileage_readings")
    mileage = models.PositiveIntegerField("kilometraje")
    previous = models.PositiveIntegerField("anterior", null=True, blank=True)
    note = models.CharField("nota", max_length=200, blank=True)
    recorded_at = models.DateTimeField("fecha")
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")

    class Meta:
        ordering = ["-recorded_at", "-id"]
        verbose_name = "lectura de kilometraje"
        verbose_name_plural = "lecturas de kilometraje"

    def __str__(self):
        return f"{self.motorcycle}: {self.mileage} km"
