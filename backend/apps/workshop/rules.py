"""Reglas de los datos de una moto (spec 009, regla 4)."""
import re

from django.core.exceptions import ValidationError
from django.utils import timezone

# Placas de moto en Colombia: ABC12D (desde 2005) o ABC12 (antes). Se aceptan de 4 a 8 letras y
# números para no rechazar placas especiales o de otro país.
PLATE = re.compile(r"[A-Z0-9]{4,8}")
# El chasis (VIN) normal tiene 17 caracteres, pero en motos viejas o importadas varía.
VIN = re.compile(r"[A-Z0-9]{6,20}")
FIRST_YEAR = 1950

# Sugerencias para el campo de marca (texto libre).
BRANDS = [
    "AKT", "Auteco", "Bajaj", "Hero", "Honda", "Kawasaki", "KTM", "Royal Enfield",
    "Suzuki", "TVS", "Victory", "Yamaha",
]


def normalize_code(value):
    """Mayúsculas, sin espacios, guiones ni puntos: `xyz-12a` y `XYZ 12A` son la misma placa."""
    return re.sub(r"[\s.\-]", "", value or "").upper()


def clean_motorcycle(data):
    """Normaliza y valida los datos de una moto (dict). Devuelve el dict normalizado."""
    plate, vin = normalize_code(data.get("plate")), normalize_code(data.get("vin"))
    errors = {}
    if plate and not PLATE.fullmatch(plate):
        errors["plate"] = "La placa debe tener de 4 a 8 letras o números, p. ej. ABC12D."
    if vin and not VIN.fullmatch(vin):
        errors["vin"] = "El chasis debe tener de 6 a 20 letras o números."
    if not plate and not vin:
        errors["vin"] = "Sin placa, el número de chasis es obligatorio."
    year = data.get("year")
    if year is not None and not FIRST_YEAR <= year <= timezone.localdate().year + 1:
        errors["year"] = f"El año debe estar entre {FIRST_YEAR} y {timezone.localdate().year + 1}."
    if not (data.get("brand") or "").strip():
        errors["brand"] = "La marca es obligatoria."
    if errors:
        raise ValidationError(errors)
    return {**data, "plate": plate, "vin": vin, "brand": data["brand"].strip(), "model": (data.get("model") or "").strip()}
