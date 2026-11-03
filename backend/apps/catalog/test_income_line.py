"""Versión sencilla y línea de ingreso (spec 013, T1): Repuestos, Taller o Lavadero."""
import importlib
import uuid
from decimal import Decimal

import pytest
from django.apps import apps as django_apps
from django.db import IntegrityError, transaction
from rest_framework.test import APIClient

from apps.inventory.models import StockMovement
from apps.inventory.services import record_movement
from apps.invoicing.models import Business
from apps.sales.models import SaleLine
from apps.sales.services import create_sale

from .models import Category, Product, Unit

pytestmark = pytest.mark.django_db
URL = "/api/catalog/admin/products/"
GOODS, WORKSHOP, WASH = Product.IncomeLine.GOODS, Product.IncomeLine.WORKSHOP, Product.IncomeLine.WASH


def api(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.fixture
def admin(make_user):
    return make_user("dueno", "Administrador")


def service(sku, category="Lavadero", **over):
    return Product.objects.create(
        sku=sku, name=f"Servicio {sku}", category=Category.objects.get_or_create(name=category)[0],
        base_unit=Unit.objects.get(code="und"), sale_price=Decimal("12000"), is_service=True, **over,
    )


def body(**over):
    category = Category.objects.get_or_create(name="Lavadero")[0]
    return {"sku": "LAV-AC", "name": "Lavado alto cilindraje", "category": category.pk, "base_unit": "und",
            "sale_price": "18000", "is_service": True, **over}


def sell(products, warehouse, shift, user):
    for p in products:
        if not p.is_service:
            record_movement(kind=StockMovement.Kind.RECEIPT, product=p, warehouse=warehouse, quantity=5, user=user, unit_cost="1000")
    total = sum(p.sale_price for p in products)
    sale, _ = create_sale(user=user, shift=shift, client_uuid=uuid.uuid4(),
                          lines=[{"product": p, "quantity": Decimal("1")} for p in products],
                          payments=[{"method": "CASH", "amount": str(total)}])
    return sale


# --- la línea del producto ------------------------------------------------------

def test_a_product_with_stock_is_always_goods(hammer):
    assert hammer.income_line == GOODS
    hammer.income_line = WASH
    hammer.save()
    hammer.refresh_from_db()
    assert hammer.income_line == GOODS


def test_a_service_is_workshop_by_default_or_wash_if_chosen():
    assert service("MO-1").income_line == WORKSHOP
    assert service("LAV-1", income_line=WASH).income_line == WASH


def test_the_database_refuses_a_line_that_does_not_match(hammer):
    wash = service("LAV-1", income_line=WASH)
    with transaction.atomic(), pytest.raises(IntegrityError):
        Product.objects.filter(pk=wash.pk).update(income_line=GOODS)
    with transaction.atomic(), pytest.raises(IntegrityError):
        Product.objects.filter(pk=hammer.pk).update(income_line=WORKSHOP)


def test_the_django_admin_fits_the_line_before_checking_constraints():
    wash = service("LAV-1", income_line=WASH)
    wash.income_line = GOODS
    wash.full_clean()  # el admin valida las restricciones antes de save() (MEMORY.md)
    assert wash.income_line == WORKSHOP


def test_the_owner_chooses_the_line_of_a_service_in_the_app(admin):
    res = api(admin).post(URL, body(income_line="WASH"), format="json")
    assert res.status_code == 201, res.data
    assert res.data["income_line"] == "WASH"
    pk = res.data["id"]
    res = api(admin).patch(f"{URL}{pk}/", {"income_line": "WORKSHOP"}, format="json")
    assert res.status_code == 200, res.data
    assert Product.objects.get(pk=pk).income_line == WORKSHOP
    till = {p["sku"]: p for p in api(admin).get("/api/catalog/products/").data}
    assert till["LAV-AC"]["income_line"] == "WORKSHOP"


def test_a_new_service_without_a_line_is_workshop(admin):
    res = api(admin).post(URL, body(), format="json")
    assert res.status_code == 201, res.data
    assert res.data["income_line"] == "WORKSHOP"


# --- la venta copia la línea ----------------------------------------------------

def test_the_sale_keeps_the_line_it_had_when_sold(admin, hammer, warehouse, shift):
    labor, wash = service("MO-1", category="Taller"), service("LAV-1", income_line=WASH)
    sale = sell([hammer, labor, wash], warehouse, shift, admin)
    assert {line.product.sku: line.income_line for line in sale.lines.all()} == {
        hammer.sku: GOODS, "MO-1": WORKSHOP, "LAV-1": WASH,
    }
    wash.income_line = WORKSHOP
    wash.save()
    assert SaleLine.objects.get(sale=sale, product=wash).income_line == WASH


# --- la casilla del negocio -----------------------------------------------------

def test_simple_mode_reaches_the_session_and_starts_off(admin):
    assert Business.load().simple_mode is False
    assert api(admin).get("/api/auth/me/").data["simple_mode"] is False
    business = Business.load()
    business.simple_mode = True
    business.save()
    assert api(admin).get("/api/auth/me/").data["simple_mode"] is True


# --- los datos que ya existían (migraciones) -------------------------------------

def test_existing_services_get_their_line(admin, hammer, warehouse, shift):
    wash, labor = service("LAV-1"), service("MO-1", category="Taller")
    sale = sell([hammer, wash, labor], warehouse, shift, admin)
    # Cada servicio con la línea equivocada (sin pasar por save()); la restricción no deja ponerlos en Repuestos,
    # que es como quedan de verdad antes de la migración.
    Product.objects.filter(pk=wash.pk).update(income_line=WORKSHOP)
    Product.objects.filter(pk=labor.pk).update(income_line=WASH)
    SaleLine.objects.filter(sale=sale).update(income_line=GOODS)
    catalog = importlib.import_module("apps.catalog.migrations.0006_income_line")
    sales = importlib.import_module("apps.sales.migrations.0014_saleline_income_line")

    catalog.fill_income_line(django_apps, None)
    sales.fill_income_line(django_apps, None)

    assert dict(Product.objects.filter(is_service=True).values_list("sku", "income_line")) == {"LAV-1": WASH, "MO-1": WORKSHOP}
    assert {line.product.sku: line.income_line for line in sale.lines.all()} == {
        hammer.sku: GOODS, "LAV-1": WASH, "MO-1": WORKSHOP,
    }
