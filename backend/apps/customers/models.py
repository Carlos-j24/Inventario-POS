from django.db import models

from .rules import FINAL_CONSUMER_NUMBER, clean_customer


class Customer(models.Model):
    """Cliente para los documentos de la DIAN. El consumidor final (222222222222) lo crea una migración."""

    class IdType(models.TextChoices):  # códigos de la DIAN
        CIVIL_REGISTRY = "11", "Registro civil"
        IDENTITY_CARD = "12", "Tarjeta de identidad"
        CITIZEN_ID = "13", "Cédula de ciudadanía"
        FOREIGNER_CARD = "21", "Tarjeta de extranjería"
        FOREIGNER_ID = "22", "Cédula de extranjería"
        NIT = "31", "NIT"
        PASSPORT = "41", "Pasaporte"
        FOREIGN_ID = "42", "Documento de identificación extranjero"
        PEP = "47", "PEP"
        PPT = "48", "PPT (Permiso por protección temporal)"
        FOREIGN_NIT = "50", "NIT de otro país"

    class PersonType(models.TextChoices):
        LEGAL = "1", "Persona jurídica"
        NATURAL = "2", "Persona natural"

    id_type = models.CharField("tipo de documento", max_length=2, choices=IdType.choices, default=IdType.CITIZEN_ID)
    id_number = models.CharField("número de documento", max_length=20)
    check_digit = models.CharField("dígito de verificación", max_length=1, blank=True)
    person_type = models.CharField("tipo de persona", max_length=1, choices=PersonType.choices, default=PersonType.NATURAL)
    name = models.CharField("nombre o razón social", max_length=200)
    email = models.EmailField("correo", blank=True, help_text="Para enviarle el documento electrónico.")
    phone = models.CharField("teléfono", max_length=30, blank=True)
    address = models.CharField("dirección", max_length=200, blank=True)
    city = models.CharField("ciudad", max_length=80, blank=True)
    tax_responsibilities = models.JSONField(
        "responsabilidades fiscales", default=list, blank=True, help_text="Códigos de la DIAN, p. ej. O-13 o R-99-PN.",
    )
    is_active = models.BooleanField("activo", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "cliente"
        constraints = [
            models.UniqueConstraint(
                fields=["id_type", "id_number"], name="unique_customer_document",
                violation_error_message="Ya existe un cliente con ese documento.",
            ),
        ]

    def __str__(self):
        number = f"{self.id_number}-{self.check_digit}" if self.check_digit else self.id_number
        return f"{self.name} ({self.get_id_type_display()} {number})"

    @property
    def is_final_consumer(self):
        return self.id_number == FINAL_CONSUMER_NUMBER

    def clean(self):
        data = clean_customer({
            "id_type": self.id_type, "id_number": self.id_number, "check_digit": self.check_digit,
            "person_type": self.person_type, "name": self.name, "tax_responsibilities": self.tax_responsibilities,
        })
        self.id_number, self.check_digit, self.name = data["id_number"], data["check_digit"], data["name"]
