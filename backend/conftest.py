from decimal import Decimal

import pytest
from django.core.cache import cache

from apps.accounts.models import Role, User
from apps.cash.models import CashRegister
from apps.cash.services import open_shift
from apps.catalog.models import Category, Product, ProductUnit, Unit
from apps.inventory.models import Warehouse


@pytest.fixture(autouse=True)
def clear_cache():
    """El límite de intentos de inicio de sesión vive en la caché: cada test empieza de cero."""
    cache.clear()


@pytest.fixture
def make_user(db):
    def _make(username="usuario", *roles):
        user = User.objects.create_user(username=username, password="clave-de-prueba-123")
        user.roles.set(Role.objects.filter(name__in=roles))
        return user

    return _make


@pytest.fixture
def warehouse(db):
    return Warehouse.objects.create(code="PRAL", name="Bodega principal")


@pytest.fixture
def register(warehouse):
    return CashRegister.objects.create(code="CAJA1", name="Caja 1", warehouse=warehouse)


@pytest.fixture
def shift(register, make_user):
    return open_shift(register=register, user=make_user("apertura", "Caja"), opening_float=Decimal("100000"))


@pytest.fixture
def cable(db):
    """Cable que se vende por metro y se compra por rollo de 100 m."""
    product = Product.objects.create(
        sku="CAB-12",
        name="Cable THHN calibre 12",
        category=Category.objects.create(name="Eléctricos"),
        base_unit=Unit.objects.get(code="m"),
        sale_price=Decimal("3200"),
        allows_fractions=True,
        min_stock=Decimal("50"),
    )
    ProductUnit.objects.create(product=product, unit=Unit.objects.get(code="rollo"), factor=Decimal("100"))
    return product


@pytest.fixture
def hammer(db):
    return Product.objects.create(
        sku="MAR-16",
        name="Martillo 16 oz",
        category=Category.objects.create(name="Herramientas"),
        base_unit=Unit.objects.get(code="und"),
        sale_price=Decimal("28000"),
    )
