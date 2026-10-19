"""Administración del catálogo desde la app (spec 006, T1)."""
import uuid
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.inventory.models import StockMovement
from apps.inventory.services import record_movement
from apps.sales.services import create_sale

from .models import Category, PriceChange, Product, ProductUnit, Unit

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
def jefe(make_user):
    """Jefe de bodega: catalog.edit sin catalog.edit_prices."""
    return make_user("jefe", "Jefe de bodega")


@pytest.fixture
def tools(db):
    return Category.objects.create(name="Herramientas")


def body(tools, **over):
    return {"sku": "DES-PH2", "name": "Destornillador estrella PH2", "category": tools.pk, "base_unit": "und", **over}


def receive(product, warehouse, user, qty=10):
    record_movement(kind=StockMovement.Kind.RECEIPT, product=product, warehouse=warehouse, quantity=qty, user=user, unit_cost="1000")


# --- crear y precios ---------------------------------------------------------

def test_with_price_permission_the_product_is_active_and_starts_its_history(admin, tools):
    res = api(admin).post(URL, body(tools, sale_price="12500", tax_rate="19", barcode=" 7701234 "), format="json")
    assert res.status_code == 201, res.data
    assert (res.data["is_active"], res.data["price_pending"], res.data["sale_price"], res.data["barcode"]) == (True, False, "12500.00", "7701234")
    assert res.data["category_name"] == "Herramientas"
    history = PriceChange.objects.get(product_id=res.data["id"])
    assert (history.old_price, history.new_price, history.user) == (None, Decimal("12500.00"), admin)


def test_a_priced_product_needs_its_price(admin, tools):
    res = api(admin).post(URL, body(tools), format="json")
    assert res.status_code == 400
    assert "Indica el precio" in str(res.data["sale_price"])


def test_without_price_permission_it_is_created_inactive_pending_price(jefe, tools):
    res = api(jefe).post(URL, body(tools, is_active=True), format="json")
    assert res.status_code == 201, res.data
    assert (res.data["is_active"], res.data["price_pending"], res.data["sale_price"]) == (False, True, "0.00")
    assert not PriceChange.objects.exists()
    for field, value in (("sale_price", "100"), ("tax_rate", "5"), ("vat_excluded", True)):
        res = api(jefe).post(URL, body(tools, sku=f"X-{field}", **{field: value}), format="json")
        assert res.status_code == 403, field


def test_pending_product_is_activated_after_the_owner_prices_it(admin, jefe, tools):
    pid = api(jefe).post(URL, body(tools), format="json").data["id"]
    res = api(jefe).patch(f"{URL}{pid}/", {"is_active": True}, format="json")
    assert res.status_code == 400
    assert "pendiente de precio" in str(res.data["is_active"])
    assert api(jefe).patch(f"{URL}{pid}/", {"sale_price": "9000"}, format="json").status_code == 403

    res = api(admin).patch(f"{URL}{pid}/", {"sale_price": "9000"}, format="json")
    assert (res.data["price_pending"], res.data["is_active"]) == (False, False)
    res = api(jefe).patch(f"{URL}{pid}/", {"is_active": True}, format="json")
    assert (res.status_code, res.data["is_active"]) == (200, True)
    change = PriceChange.objects.get(product_id=pid)
    assert (change.old_price, change.new_price, change.user) == (Decimal("0.00"), Decimal("9000.00"), admin)


def test_a_pending_product_priced_at_zero_stops_being_pending(admin, jefe, tools):
    pid = api(jefe).post(URL, body(tools), format="json").data["id"]
    res = api(admin).patch(f"{URL}{pid}/", {"sale_price": "0"}, format="json")  # p. ej. un obsequio
    assert res.data["price_pending"] is False
    assert PriceChange.objects.filter(product_id=pid).count() == 1


def test_each_price_change_is_recorded_once(admin, jefe, hammer):
    client = api(admin)
    client.patch(f"{URL}{hammer.pk}/", {"sale_price": "29000"}, format="json")
    client.patch(f"{URL}{hammer.pk}/", {"sale_price": "29000", "name": "Martillo de uña 16 oz"}, format="json")  # mismo precio
    client.patch(f"{URL}{hammer.pk}/", {"sale_price": "31000"}, format="json")
    history = api(jefe).get(f"{URL}{hammer.pk}/price-history/").data
    assert [(h["old_price"], h["new_price"], h["user"]) for h in history] == [
        ("29000.00", "31000.00", "dueno"), ("28000.00", "29000.00", "dueno"),
    ]
    hammer.refresh_from_db()
    assert hammer.name == "Martillo de uña 16 oz"


def test_jefe_edits_everything_but_price_and_vat(jefe, hammer):
    res = api(jefe).patch(f"{URL}{hammer.pk}/", {"name": "Martillo 20 oz", "min_stock": "4", "allows_fractions": False}, format="json")
    assert (res.status_code, res.data["name"], res.data["min_stock"]) == (200, "Martillo 20 oz", "4.000")
    assert api(jefe).patch(f"{URL}{hammer.pk}/", {"tax_rate": "0"}, format="json").status_code == 403


def test_excluded_only_with_zero_rate(admin, hammer):
    res = api(admin).patch(f"{URL}{hammer.pk}/", {"vat_excluded": True}, format="json")
    assert res.status_code == 400
    assert api(admin).patch(f"{URL}{hammer.pk}/", {"vat_excluded": True, "tax_rate": "0"}, format="json").status_code == 200


# --- lo que no cambia con movimientos ----------------------------------------

def test_sku_and_base_unit_are_fixed_once_there_are_movements(admin, hammer, warehouse):
    client = api(admin)
    assert client.patch(f"{URL}{hammer.pk}/", {"sku": "MAR-16-B"}, format="json").status_code == 200  # sin movimientos
    receive(hammer, warehouse, admin)
    res = client.patch(f"{URL}{hammer.pk}/", {"sku": "MAR-16-C"}, format="json")
    assert res.status_code == 400 and "SKU" in str(res.data["sku"])
    res = client.patch(f"{URL}{hammer.pk}/", {"base_unit": "kg"}, format="json")
    assert res.status_code == 400 and "unidad base" in str(res.data["base_unit"])
    assert client.patch(f"{URL}{hammer.pk}/", {"sku": "MAR-16-B", "base_unit": "und"}, format="json").status_code == 200  # sin cambios
    assert client.get(f"{URL}{hammer.pk}/").data["has_movements"] is True


# --- códigos de barras ---------------------------------------------------------

def test_barcodes_are_unique_across_products_and_presentations(admin, hammer, cable):
    client = api(admin)
    rollo = cable.units.get()
    ProductUnit.objects.filter(pk=rollo.pk).update(barcode="ROLLO-12")
    res = client.patch(f"{URL}{hammer.pk}/", {"barcode": "ROLLO-12"}, format="json")
    assert res.status_code == 400 and "ROLLO-12" in str(res.data["barcode"])
    Product.objects.filter(pk=hammer.pk).update(barcode="MAR-BAR")
    res = client.patch(f"/api/catalog/admin/units/{rollo.pk}/", {"barcode": "MAR-BAR"}, format="json")
    assert res.status_code == 400
    assert client.patch(f"{URL}{hammer.pk}/", {"barcode": "MAR-BAR"}, format="json").status_code == 200  # el suyo
    assert client.patch(f"/api/catalog/admin/units/{rollo.pk}/", {"barcode": "ROLLO-12"}, format="json").status_code == 200


# --- presentaciones ------------------------------------------------------------

def test_presentation_factor_is_fixed_once_used(admin, cable, warehouse, shift):
    client = api(admin)
    rollo = cable.units.get()
    res = client.patch(f"/api/catalog/admin/units/{rollo.pk}/", {"factor": "50"}, format="json")
    assert (res.status_code, res.data["factor"], res.data["in_use"]) == (200, "50.000", False)  # sin usar: se puede
    client.patch(f"/api/catalog/admin/units/{rollo.pk}/", {"factor": "100"}, format="json")

    receive(cable, warehouse, admin, qty=500)
    create_sale(user=admin, shift=shift, client_uuid=uuid.uuid4(), lines=[{"product": cable, "unit": Unit.objects.get(code="rollo"), "quantity": Decimal("1")}],
                payments=[{"method": "CASH", "amount": "400000"}])
    res = client.patch(f"/api/catalog/admin/units/{rollo.pk}/", {"factor": "50"}, format="json")
    assert res.status_code == 400 and "Desactívala" in str(res.data["factor"])
    assert client.patch(f"/api/catalog/admin/units/{rollo.pk}/", {"factor": "100.000"}, format="json").status_code == 200  # el mismo
    assert client.delete(f"/api/catalog/admin/units/{rollo.pk}/").status_code == 400
    res = client.patch(f"/api/catalog/admin/units/{rollo.pk}/", {"is_active": False}, format="json")
    assert (res.status_code, res.data["is_active"], res.data["in_use"]) == (200, False, True)
    pos = {p["sku"]: p for p in client.get("/api/catalog/products/").data}
    assert pos["CAB-12"]["units"] == []  # la caja ya no la ofrece


def test_add_and_delete_an_unused_presentation(admin, hammer):
    client = api(admin)
    res = client.post(f"{URL}{hammer.pk}/units/", {"unit": "caja", "factor": "12", "barcode": "CAJA-MAR"}, format="json")
    assert (res.status_code, res.data["unit"], res.data["factor"]) == (201, "caja", "12.000")
    assert client.post(f"{URL}{hammer.pk}/units/", {"unit": "caja", "factor": "6"}, format="json").status_code == 400  # repetida
    assert client.post(f"{URL}{hammer.pk}/units/", {"unit": "und", "factor": "1"}, format="json").status_code == 400  # la base
    assert client.post(f"{URL}{hammer.pk}/units/", {"unit": "bulto", "factor": "5", "barcode": "CAJA-MAR"}, format="json").status_code == 400
    assert client.delete(f"/api/catalog/admin/units/{res.data['id']}/").status_code == 204
    assert not hammer.units.exists()


# --- categorías, unidades y listado ---------------------------------------------

def test_categories(admin, hammer):
    client = api(admin)
    res = client.post("/api/catalog/categories/", {"name": "  Pinturas   y  solventes "}, format="json")
    assert (res.status_code, res.data["name"], res.data["products"]) == (201, "Pinturas y solventes", 0)
    assert client.post("/api/catalog/categories/", {"name": "Pinturas y solventes"}, format="json").status_code == 400
    assert client.patch(f"/api/catalog/categories/{res.data['id']}/", {"name": "Pinturas"}, format="json").data["name"] == "Pinturas"
    assert client.delete(f"/api/catalog/categories/{hammer.category_id}/").status_code == 400  # tiene productos
    assert client.delete(f"/api/catalog/categories/{res.data['id']}/").status_code == 204
    assert "und" in [u["code"] for u in client.get("/api/catalog/units/").data]


def test_admin_list_search_and_filters(admin, hammer, cable):
    Product.objects.filter(pk=cable.pk).update(is_active=False, barcode="7700001")
    ProductUnit.objects.filter(product=cable).update(barcode="ROLLO-12")
    client = api(admin)
    skus = lambda **q: [p["sku"] for p in client.get(URL, q).data]  # noqa: E731
    assert skus() == ["CAB-12", "MAR-16"]
    assert skus(q="martillo") == ["MAR-16"]
    assert skus(q="cab") == ["CAB-12"]
    assert skus(q="7700001") == ["CAB-12"]
    assert skus(q="ROLLO-12") == ["CAB-12"]  # código de la presentación
    assert skus(active="1") == ["MAR-16"]
    assert skus(active="0") == ["CAB-12"]
    assert skus(category=hammer.category_id) == ["MAR-16"]


def test_permissions(make_user, hammer):
    assert api(make_user("vende", "Ventas")).get(URL).status_code == 403  # ve inventario, no edita catálogo
    cashier = make_user("caja", "Caja")
    assert api(cashier).get(URL).status_code == 403
    assert api(cashier).patch(f"{URL}{hammer.pk}/", {"name": "x"}, format="json").status_code == 403
    assert api(cashier).get("/api/catalog/categories/").status_code == 403
    counter = make_user("cuenta", "Auxiliar de bodega")  # cuenta inventario: ve las categorías, no las crea
    assert api(counter).get("/api/catalog/categories/").status_code == 200
    assert api(counter).post("/api/catalog/categories/", {"name": "Nueva"}, format="json").status_code == 403
    assert api(cashier).get("/api/catalog/products/").status_code == 200  # el catálogo del POS sigue igual
    assert APIClient().get(URL).status_code == 403
