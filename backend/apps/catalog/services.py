"""Administración del catálogo desde la app (spec 006, T1).

Reglas:
- El SKU y la unidad base no cambian si el producto ya tiene movimientos (kardex, reportes).
- El factor de una presentación usada en ventas o pedidos no cambia y no se borra: se desactiva.
- Un código de barras es único entre productos y presentaciones juntos.
- Precio, tarifa de IVA y excluido solo con catalog.edit_prices; cada cambio de precio queda en el
  historial. Quien no tiene ese permiso crea el producto inactivo y "pendiente de precio".
- Un servicio (spec 010) no tiene stock mínimo, fracciones ni presentaciones, y producto y servicio
  no se intercambian si ya hay movimientos o ventas (las reglas están en el modelo).
"""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.inventory.models import StockMovement
from apps.sales.models import OrderLine, SaleLine

from .models import Category, PriceChange, Product, ProductUnit

PRICE_FIELDS = ("sale_price", "tax_rate", "vat_excluded")
EDITABLE = ("sku", "name", "category", "base_unit", "barcode", "allows_fractions", "min_stock", "is_active", "is_service", *PRICE_FIELDS)


def can_edit_prices(user):
    return user.has_app_permission("catalog.edit_prices")


def has_movements(product):
    return StockMovement.objects.filter(product=product).exists()


def unit_in_use(presentation):
    """Ya hay ventas o pedidos en esa presentación: su factor quedó en esos documentos."""
    lookup = {"product_id": presentation.product_id, "unit_id": presentation.unit_id}
    return SaleLine.objects.filter(**lookup).exists() or OrderLine.objects.filter(**lookup).exists()


def check_barcode(code, *, product=None, presentation=None):
    """Un código de barras no puede repetirse entre productos ni presentaciones."""
    if not code:
        return None
    products = Product.objects.filter(barcode=code)
    units = ProductUnit.objects.filter(barcode=code)
    if product is not None:
        products = products.exclude(pk=product.pk)
    if presentation is not None:
        units = units.exclude(pk=presentation.pk)
    if products.exists() or units.exists():
        raise ValidationError({"barcode": f"El código de barras {code} ya está en otro producto o presentación."})
    return code


def _require_prices(user, data):
    touched = [f for f in PRICE_FIELDS if f in data]
    if touched and not can_edit_prices(user):
        raise PermissionDenied("Cambiar el precio o el IVA requiere el permiso 'catalog.edit_prices'.")


def create_product(*, user, data):
    """Crea un producto. Sin permiso de precios, queda inactivo y pendiente de precio."""
    _require_prices(user, data)
    data = {k: v for k, v in data.items() if k in EDITABLE}
    with transaction.atomic():
        product = Product(**data)
        product.barcode = check_barcode(product.barcode)
        if can_edit_prices(user):
            if "sale_price" not in data:
                raise ValidationError({"sale_price": "Indica el precio de venta."})
        else:
            product.sale_price, product.price_pending, product.is_active = 0, True, False
        product.full_clean()
        product.save()
        if not product.price_pending:
            PriceChange.objects.create(product=product, old_price=None, new_price=product.sale_price, user=user)
    return product


def update_product(*, user, product, data):
    """Edita un producto con las reglas de la spec 006."""
    _require_prices(user, data)
    data = {k: v for k, v in data.items() if k in EDITABLE}
    with transaction.atomic():
        product = Product.objects.select_for_update().get(pk=product.pk)
        moved = has_movements(product)
        if moved and "sku" in data and data["sku"] != product.sku:
            raise ValidationError({"sku": "El producto ya tiene movimientos: su SKU no se puede cambiar."})
        if moved and "base_unit" in data and data["base_unit"] != product.base_unit:
            raise ValidationError({"base_unit": "El producto ya tiene movimientos: su unidad base no cambia. Crea un producto nuevo."})
        old_price = product.sale_price
        for field, value in data.items():
            setattr(product, field, value)
        if "barcode" in data:
            product.barcode = check_barcode(product.barcode, product=product)
        price_changed = "sale_price" in data and (product.price_pending or data["sale_price"] != old_price)
        if price_changed:
            product.price_pending = False
        if product.is_active and product.price_pending:
            raise ValidationError({"is_active": "Ponle precio antes de activarlo: está pendiente de precio."})
        product.full_clean()
        product.save()
        if price_changed:
            PriceChange.objects.create(product=product, old_price=old_price, new_price=product.sale_price, user=user)
    return product


def add_presentation(*, product, unit, factor, barcode=None):
    presentation = ProductUnit(product=product, unit=unit, factor=factor)
    presentation.barcode = check_barcode(barcode)
    presentation.full_clean()
    presentation.save()
    return presentation


def update_presentation(*, presentation, data):
    """Cambia factor, código o si está activa. El factor de una presentación usada no cambia."""
    with transaction.atomic():
        presentation = ProductUnit.objects.select_for_update().select_related("product").get(pk=presentation.pk)
        if "factor" in data and data["factor"] != presentation.factor and unit_in_use(presentation):
            raise ValidationError({"factor": "Esta presentación ya se usó en ventas o pedidos: su factor no cambia. Desactívala y crea otra."})
        for field in ("factor", "is_active"):
            if field in data:
                setattr(presentation, field, data[field])
        if "barcode" in data:
            presentation.barcode = check_barcode(data["barcode"], presentation=presentation)
        presentation.full_clean()
        presentation.save()
    return presentation


def delete_presentation(*, presentation):
    if unit_in_use(presentation):
        raise ValidationError("Esta presentación ya se usó en ventas o pedidos: desactívala en vez de borrarla.")
    presentation.delete()


def delete_category(*, category):
    if category.products.exists():
        raise ValidationError("La categoría tiene productos: muévelos antes de borrarla.")
    category.delete()


def rename_category(*, category, name):
    category.name = " ".join(name.split())
    category.full_clean()
    category.save()
    return category


def create_category(*, name):
    category = Category(name=" ".join(name.split()))
    category.full_clean()
    category.save()
    return category
