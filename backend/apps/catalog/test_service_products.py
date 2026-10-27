"""Servicios en el catálogo (spec 010, T1): un lavado se cobra sin mover inventario."""
import uuid
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from rest_framework.test import APIClient

from apps.inventory.models import StockMovement
from apps.inventory.services import record_movement
from apps.sales.models import SaleLine, SaleReturn, SaleReturnLine
from apps.sales.services import create_sale

from .models import Category, Product, ProductUnit, Unit

pytestmark = pytest.mark.django_db
URL = "/api/catalog/admin/products/"


def api(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.fixture
def admin(make_user):
    return make_user("dueno", "Administrador")


@pytest.fixture
def wash(db):
    return Product.objects.create(
        sku="LAV-150", name="Lavado moto hasta 150 cc", category=Category.objects.create(name="Lavadero"),
        base_unit=Unit.objects.get(code="und"), sale_price=Decimal("12000"), is_service=True,
    )


def service_body(**over):
    category = Category.objects.get_or_create(name="Lavadero")[0]
    return {"sku": "LAV-AC", "name": "Lavado alto cilindraje", "category": category.pk, "base_unit": "und",
            "sale_price": "18000", "is_service": True, **over}


def sell(product, warehouse, shift, user):
    """Una venta del producto (con su entrada antes), para tener movimientos y una línea vendida."""
    record_movement(kind=StockMovement.Kind.RECEIPT, product=product, warehouse=warehouse, quantity=5, user=user, unit_cost="1000")
    sale, _ = create_sale(user=user, shift=shift, client_uuid=uuid.uuid4(), lines=[{"product": product, "quantity": Decimal("1")}],
                          payments=[{"method": "CASH", "amount": str(product.sale_price)}])
    return sale


def service_line(sale, product, **over):
    """Una línea de servicio a mano: vender servicios en la caja es la T2."""
    data = {"sale": sale, "product": product, "unit": product.base_unit, "quantity": 1, "unit_price": product.sale_price,
            "catalog_price": product.sale_price, "tax_rate": 19, "subtotal": 0, "tax": 0, "total": product.sale_price,
            "is_service": True, "movement": None, **over}
    return SaleLine.objects.create(**data)


# --- crear y ver -------------------------------------------------------------

def test_the_owner_creates_a_service_and_the_till_sees_it(admin):
    res = api(admin).post(URL, service_body(), format="json")
    assert res.status_code == 201, res.data
    assert (res.data["is_service"], res.data["is_active"], res.data["min_stock"]) == (True, True, "0.000")
    till = {p["sku"]: p for p in api(admin).get("/api/catalog/products/").data}
    assert till["LAV-AC"]["is_service"] is True


def test_products_are_not_services_by_default(admin, hammer):
    assert api(admin).get(f"{URL}{hammer.pk}/").data["is_service"] is False
    till = {p["sku"]: p for p in api(admin).get("/api/catalog/products/").data}
    assert till["MAR-16"]["is_service"] is False


def test_a_service_has_no_fractions_or_minimum_stock(admin):
    res = api(admin).post(URL, service_body(allows_fractions=True), format="json")
    assert res.status_code == 400 and "unidad entera" in str(res.data["allows_fractions"])
    res = api(admin).post(URL, service_body(min_stock="2"), format="json")
    assert res.status_code == 400 and "stock mínimo" in str(res.data["min_stock"])
    assert not Product.objects.filter(sku="LAV-AC").exists()


def test_the_database_also_refuses_a_service_with_stock_rules(wash):
    for field, value in (("allows_fractions", True), ("min_stock", Decimal("1"))):
        with pytest.raises(IntegrityError), transaction.atomic():
            Product.objects.filter(pk=wash.pk).update(**{field: value})


def test_a_service_takes_no_presentations(admin, wash):
    res = api(admin).post(f"{URL}{wash.pk}/units/", {"unit": "caja", "factor": "10"}, format="json")
    assert res.status_code == 400 and "no lleva presentaciones" in str(res.data)
    assert not wash.units.exists()
    with pytest.raises(ValidationError, match="no lleva presentaciones"):  # también en el admin de Django
        ProductUnit(product=wash, unit=Unit.objects.get(code="caja"), factor=Decimal("10")).full_clean()


# --- producto ↔ servicio -------------------------------------------------------

def test_an_unused_product_can_become_a_service_and_back(admin, hammer):
    res = api(admin).patch(f"{URL}{hammer.pk}/", {"is_service": True}, format="json")
    assert (res.status_code, res.data["is_service"]) == (200, True)
    res = api(admin).patch(f"{URL}{hammer.pk}/", {"is_service": False}, format="json")
    assert (res.status_code, res.data["is_service"]) == (200, False)


def test_a_product_with_movements_does_not_become_a_service(admin, hammer, warehouse, shift):
    sell(hammer, warehouse, shift, admin)
    res = api(admin).patch(f"{URL}{hammer.pk}/", {"is_service": True}, format="json")
    assert res.status_code == 400 and "movimientos de inventario" in str(res.data["is_service"])
    hammer.refresh_from_db()
    assert hammer.is_service is False


def test_only_receipts_are_enough_to_keep_it_a_product(admin, hammer, warehouse):
    record_movement(kind=StockMovement.Kind.RECEIPT, product=hammer, warehouse=warehouse, quantity=5, user=admin, unit_cost="1000")
    assert api(admin).patch(f"{URL}{hammer.pk}/", {"is_service": True}, format="json").status_code == 400


def test_a_product_with_presentations_must_drop_them_first(admin, cable):
    res = api(admin).patch(f"{URL}{cable.pk}/", {"is_service": True, "allows_fractions": False, "min_stock": "0"}, format="json")
    assert res.status_code == 400 and "presentaciones" in str(res.data["is_service"])


def test_a_service_with_sales_does_not_become_a_product(admin, hammer, wash, warehouse, shift):
    service_line(sell(hammer, warehouse, shift, admin), wash)
    res = api(admin).patch(f"{URL}{wash.pk}/", {"is_service": False}, format="json")
    assert res.status_code == 400 and "ya tiene ventas" in str(res.data["is_service"])
    wash.refresh_from_db()
    assert wash.is_service is True


def test_sold_products_and_services_still_edit_everything_else(admin, hammer, wash, warehouse, shift):
    service_line(sell(hammer, warehouse, shift, admin), wash)
    for item, name in ((hammer, "Martillo de uña 16 oz"), (wash, "Lavado moto hasta 150 cc (incluye brillo)")):
        res = api(admin).patch(f"{URL}{item.pk}/", {"name": name, "is_service": item.is_service}, format="json")
        assert (res.status_code, res.data["name"]) == (200, name), res.data


def test_the_rule_lives_in_the_model_for_the_django_admin(admin, hammer, warehouse, shift):
    sell(hammer, warehouse, shift, admin)
    hammer.is_service = True
    with pytest.raises(ValidationError, match="movimientos de inventario"):
        hammer.full_clean()


# --- líneas de venta sin movimiento ----------------------------------------

def test_a_service_line_has_no_movement_and_a_product_line_needs_one(admin, hammer, wash, warehouse, shift):
    sale = sell(hammer, warehouse, shift, admin)
    product_line = sale.lines.get()
    assert (product_line.is_service, product_line.movement is not None) == (False, True)
    line = service_line(sale, wash)
    assert (line.is_service, line.movement) == (True, None)
    with pytest.raises(IntegrityError), transaction.atomic():
        service_line(sale, hammer, is_service=False)  # producto sin movimiento
    with pytest.raises(IntegrityError), transaction.atomic():
        SaleLine.objects.filter(pk=line.pk).update(movement=product_line.movement, is_service=True)  # servicio con movimiento


def test_a_return_line_of_a_service_has_no_movement(admin, hammer, wash, warehouse, shift):
    sale = sell(hammer, warehouse, shift, admin)
    line = service_line(sale, wash)
    back = SaleReturn.objects.create(client_uuid=uuid.uuid4(), sale=sale, shift=shift, user=admin, reason="No se lavó",
                                     total=line.total)
    returned = SaleReturnLine.objects.create(sale_return=back, sale_line=line, quantity=1, subtotal=0, tax=0, total=line.total)
    assert returned.movement is None
