"""Búsquedas de clientes que comparten la caja y el taller."""
import re

from django.db.models import F, Q, Value
from django.db.models.functions import Replace

SEPARATORS = (" ", "-", ".", "(", ")")


def phone_digits(field="phone"):
    """El teléfono sin espacios, guiones, puntos ni paréntesis, para buscar "300 123-4567" con "3001234567"."""
    expression = F(field)
    for char in SEPARATORS:
        expression = Replace(expression, Value(char), Value(""))
    return expression


def only_digits(query):
    """Los dígitos de lo que se escribió si es un número (cédula o teléfono); si no, None."""
    digits = re.sub(r"[\s.\-()+]", "", query)
    return digits if digits.isdigit() else None


def number_or_phone(digits, prefix=""):
    """Documento que empieza por esos dígitos o teléfono que los contiene.

    Antes hay que anotar `phone_digits` (con `phone_digits("<prefix>phone")`) en lo que se busca.
    """
    return Q(**{f"{prefix}id_number__startswith": digits}) | Q(phone_digits__contains=digits)
