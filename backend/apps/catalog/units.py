from decimal import Decimal

from django.core.exceptions import ValidationError

from .models import ProductUnit


def to_base_quantity(product, quantity, unit=None):
    """Convierte una cantidad en cualquier presentación del producto a su unidad base."""
    quantity = Decimal(quantity)
    if unit is None or unit.pk == product.base_unit_id:
        factor = Decimal(1)
    else:
        try:
            factor = product.units.get(unit=unit).factor
        except ProductUnit.DoesNotExist:
            raise ValidationError(f"{product.sku} no se maneja en la unidad '{unit}'.")
    base = quantity * factor
    if not product.allows_fractions and base != base.to_integral_value():
        raise ValidationError(f"{product.sku} no se vende fraccionado.")
    return base
