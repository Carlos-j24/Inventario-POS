from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
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


# --- Órdenes de trabajo (spec 011) ----------------------------------------------------------------

class WorkOrder(models.Model):
    """Una moto en el taller, desde que entra hasta que sale. Solo la cambian los servicios del taller."""

    class Status(models.TextChoices):
        RECEIVED = "RECEIVED", "Recibida"
        AWAITING_APPROVAL = "AWAITING_APPROVAL", "Esperando aprobación"
        IN_REPAIR = "IN_REPAIR", "En reparación"
        READY = "READY", "Lista"
        DELIVERED = "DELIVERED", "Entregada"
        CANCELLED = "CANCELLED", "Cancelada"

    OPEN = (Status.RECEIVED, Status.AWAITING_APPROVAL, Status.IN_REPAIR, Status.READY)

    motorcycle = models.ForeignKey(Motorcycle, verbose_name="moto", on_delete=models.PROTECT, related_name="work_orders")
    # El dueño al recibirla: si la moto cambia de dueño después, la orden sigue siendo de quien la trajo.
    customer = models.ForeignKey(Customer, verbose_name="cliente", on_delete=models.PROTECT, related_name="work_orders")
    status = models.CharField("estado", max_length=20, choices=Status.choices, default=Status.RECEIVED)
    mileage_in = models.PositiveIntegerField("kilometraje de llegada")
    mileage_out = models.PositiveIntegerField("kilometraje de salida", null=True, blank=True)
    request = models.TextField("lo que pide el cliente")
    condition = models.TextField("estado al recibir", blank=True, help_text="Rayones, golpes, lo que falta y lo que deja.")
    diagnosis = models.TextField("diagnóstico", blank=True)
    mechanic = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="mecánico", on_delete=models.PROTECT, related_name="work_orders",
        null=True, blank=True,
    )
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="recibió", on_delete=models.PROTECT, related_name="+")
    received_at = models.DateTimeField("recibida", auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-received_at", "-id"]
        verbose_name = "orden de trabajo"
        verbose_name_plural = "órdenes de trabajo"
        constraints = [
            models.UniqueConstraint(
                fields=["motorcycle"], condition=Q(status__in=["RECEIVED", "AWAITING_APPROVAL", "IN_REPAIR", "READY"]),
                name="one_open_work_order_per_motorcycle",
                violation_error_message="La moto ya tiene una orden de trabajo abierta.",
            ),
        ]

    @property
    def number(self):
        return f"OT-{self.pk:06d}"

    def __str__(self):
        return f"{self.number} · {self.motorcycle}"


class WorkOrderLine(models.Model):
    """Un repuesto (producto con inventario) o mano de obra (servicio, spec 010) del presupuesto.

    La cantidad va en la unidad base. Un repuesto aprobado sale de la bodega con `movement` y, si no se
    usa, vuelve con `returned_movement` (spec 011, regla 5).
    """

    work_order = models.ForeignKey(WorkOrder, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey("catalog.Product", verbose_name="producto", on_delete=models.PROTECT, related_name="+")
    is_service = models.BooleanField(default=False, help_text="Copiado del producto: la mano de obra no sale de la bodega.")
    quantity = models.DecimalField("cantidad", max_digits=14, decimal_places=3, validators=[MinValueValidator(Decimal("0.001"))])
    unit_price = models.DecimalField("precio", max_digits=14, decimal_places=2, validators=[MinValueValidator(0)],
                                     help_text="Por unidad, IVA incluido.")
    approved = models.BooleanField("aprobada", default=False, help_text="El cliente la aprobó en el presupuesto.")
    movement = models.OneToOneField(
        "inventory.StockMovement", on_delete=models.PROTECT, related_name="work_order_line", null=True, blank=True,
    )
    returned_movement = models.OneToOneField(
        "inventory.StockMovement", on_delete=models.PROTECT, related_name="work_order_return", null=True, blank=True,
    )
    added_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        verbose_name = "línea de la orden"
        verbose_name_plural = "líneas de la orden"
        constraints = [
            models.CheckConstraint(
                condition=Q(movement__isnull=True) | Q(is_service=False, approved=True),
                name="work_order_line_out_only_approved_parts",
                violation_error_message="Solo sale de la bodega un repuesto aprobado.",
            ),
            models.CheckConstraint(
                condition=Q(returned_movement__isnull=True) | Q(movement__isnull=False),
                name="work_order_line_returns_only_what_left",
                violation_error_message="Solo vuelve a la bodega lo que salió.",
            ),
        ]

    @property
    def total(self):
        return (self.quantity * self.unit_price).quantize(Decimal("0.01"))

    def __str__(self):
        return f"{self.work_order.number}: {self.quantity} × {self.product}"


class WorkOrderApproval(models.Model):
    """El cliente aprobó el presupuesto (spec 011, decisión 2). Lo registra recepción."""

    class Channel(models.TextChoices):
        IN_PERSON = "IN_PERSON", "En persona"
        PHONE = "PHONE", "Por llamada"

    work_order = models.ForeignKey(WorkOrder, on_delete=models.CASCADE, related_name="approvals")
    approved_by = models.CharField("aprobó", max_length=120, help_text="Quién aprobó: el cliente o quien él autorizó.")
    channel = models.CharField("cómo", max_length=10, choices=Channel.choices)
    total = models.DecimalField("total aprobado", max_digits=14, decimal_places=2)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="registró", on_delete=models.PROTECT, related_name="+")
    recorded_at = models.DateTimeField("fecha", auto_now_add=True)

    class Meta:
        ordering = ["-recorded_at", "-id"]
        verbose_name = "aprobación del presupuesto"
        verbose_name_plural = "aprobaciones del presupuesto"

    def __str__(self):
        return f"{self.work_order.number}: {self.approved_by} ({self.get_channel_display()})"


class WorkOrderEvent(models.Model):
    """Cada cambio de estado, con quién y cuándo (spec 011, regla 2)."""

    work_order = models.ForeignKey(WorkOrder, on_delete=models.CASCADE, related_name="events")
    status = models.CharField("estado", max_length=20, choices=WorkOrder.Status.choices)
    note = models.CharField("nota", max_length=200, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    at = models.DateTimeField("fecha", auto_now_add=True)

    class Meta:
        ordering = ["at", "id"]
        verbose_name = "cambio de estado"
        verbose_name_plural = "cambios de estado"

    def __str__(self):
        return f"{self.work_order.number} → {self.get_status_display()}"
