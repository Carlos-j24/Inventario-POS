"""Reglas de los datos de un cliente para los documentos de la DIAN (spec 005, T1)."""
import re

from django.core.exceptions import ValidationError

# Pesos de la DIAN para el dígito de verificación, del dígito de la derecha hacia la izquierda.
DV_WEIGHTS = (3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71)

# Tipos de documento que solo llevan dígitos (los demás admiten letras: pasaporte, extranjeros).
NUMERIC_TYPES = {"11", "12", "13", "21", "22", "31"}
NIT_TYPES = {"31", "50"}

RESPONSIBILITIES = {
    "O-13": "Gran contribuyente",
    "O-15": "Autorretenedor",
    "O-23": "Agente de retención IVA",
    "O-47": "Régimen simple de tributación",
    "R-99-PN": "No responsable",
}

FINAL_CONSUMER_NUMBER = "222222222222"


def check_digit(nit):
    """Dígito de verificación de un NIT colombiano (algoritmo de la DIAN, módulo 11)."""
    digits = [int(d) for d in reversed(nit)]
    if len(digits) > len(DV_WEIGHTS):
        raise ValidationError({"id_number": "El NIT tiene demasiados dígitos."})
    remainder = sum(d * w for d, w in zip(digits, DV_WEIGHTS)) % 11
    return str(remainder if remainder < 2 else 11 - remainder)


def clean_customer(data):
    """Normaliza y valida los datos de un cliente (dict). Devuelve el dict normalizado.

    Quita puntos, guiones y espacios del número; calcula el dígito de verificación del NIT y
    rechaza uno que no coincida; una persona jurídica debe tener NIT.
    """
    id_type = data["id_type"]
    number = re.sub(r"[\s.\-]", "", data["id_number"]).upper()
    if not number:
        raise ValidationError({"id_number": "Escribe el número de documento."})
    if id_type in NUMERIC_TYPES and not number.isdigit():
        raise ValidationError({"id_number": "Este tipo de documento solo lleva dígitos."})
    if not number.isalnum():
        raise ValidationError({"id_number": "Usa solo letras y dígitos."})
    data["id_number"] = number

    given = (data.get("check_digit") or "").strip()
    if id_type == "31":
        expected = check_digit(number)
        if given and given != expected:
            raise ValidationError({"check_digit": f"El dígito de verificación de este NIT es {expected}."})
        data["check_digit"] = expected
    elif id_type != "50":
        data["check_digit"] = ""  # solo el NIT lleva dígito de verificación

    if data.get("person_type") == "1" and id_type not in NIT_TYPES:
        raise ValidationError({"person_type": "Una persona jurídica se identifica con NIT."})

    unknown = set(data.get("tax_responsibilities") or []) - set(RESPONSIBILITIES)
    if unknown:
        raise ValidationError({"tax_responsibilities": f"Responsabilidades desconocidas: {', '.join(sorted(unknown))}."})
    data["name"] = " ".join((data.get("name") or "").split())
    if not data["name"]:
        raise ValidationError({"name": "Escribe el nombre o la razón social."})
    return data
