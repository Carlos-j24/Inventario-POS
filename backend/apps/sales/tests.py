import uuid
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.catalog.models import Product, Unit
from apps.inventory.models import StockLevel, StockMovement
from apps.inventory.services import InsufficientStock, record_movement
from apps.sales.models import Sale
from apps.sales.services import create_sale

pytestmark = pytest.mark.django_db


def stock(product, warehouse):
    return StockLevel.objects.get(product=product, warehouse=warehouse).quantity


def receive(product, warehouse, user, qty):
    record_movement(kind=StockMovement.Kind.RECEIPT, product=product, warehouse=warehouse, quantity=qty, user=user)


@pytest.fixture
def seller(make_user):
    return make_user("caja1", "Caja")


@pytest.fixture
def stocked(seller, warehouse, hammer, cable):
    receive(hammer, warehouse, seller, 10)
    receive(cable, warehouse, seller, 300)


# --- servicio ---------------------------------------------------------------

def test_sale_takes_stock_and_separates_vat(seller, warehouse, hammer, stocked):
    sale, created = create_sale(
        user=seller, warehouse=warehouse, client_uuid=uuid.uuid4(),
        lines=[{"product": hammer, "quantity": 2}],
    )
    assert created
    assert stock(hammer, warehouse) == 8
    # 2 × 28.000 IVA incluido al 19 %: base 47.058,82 + IVA 8.941,18
    assert sale.total == Decimal("56000.00")
    assert sale.subtotal == Decimal("47058.82")
    assert sale.tax == Decimal("8941.18")
    assert sale.subtotal + sale.tax == sale.total
    assert not sale.needs_review


def test_selling_a_roll_uses_factor_for_price_and_stock(seller, warehouse, cable, stocked):
    sale, _ = create_sale(
        user=seller, warehouse=warehouse, client_uuid=uuid.uuid4(),
        lines=[{"product": cable, "quantity": 1, "unit": Unit.objects.get(code="rollo")}],
    )
    assert stock(cable, warehouse) == 200
    assert sale.lines.get().unit_price == Decimal("320000.00")  # 3.200 por metro × 100


def test_fractional_meters(seller, warehouse, cable, stocked):
    sale, _ = create_sale(
        user=seller, warehouse=warehouse, client_uuid=uuid.uuid4(),
        lines=[{"product": cable, "quantity": Decimal("2.5")}],
    )
    assert stock(cable, warehouse) == Decimal("297.5")
    assert sale.total == Decimal("8000.00")


def test_exempt_product_has_no_vat(seller, warehouse, hammer, stocked):
    hammer.tax_rate = Product.TaxRate.EXEMPT
    hammer.save()
    sale, _ = create_sale(
        user=seller, warehouse=warehouse, client_uuid=uuid.uuid4(),
        lines=[{"product": hammer, "quantity": 1}],
    )
    assert sale.tax == 0
    assert sale.subtotal == sale.total


def test_online_sale_without_stock_rolls_back_everything(seller, warehouse, hammer, cable, stocked):
    with pytest.raises(InsufficientStock):
        create_sale(
            user=seller, warehouse=warehouse, client_uuid=uuid.uuid4(),
            lines=[{"product": cable, "quantity": 5}, {"product": hammer, "quantity": 50}],
        )
    assert not Sale.objects.exists()
    assert stock(cable, warehouse) == 300  # la primera línea tampoco quedó


def test_online_sale_ignores_client_price(seller, warehouse, hammer, stocked):
    sale, _ = create_sale(
        user=seller, warehouse=warehouse, client_uuid=uuid.uuid4(),
        lines=[{"product": hammer, "quantity": 1, "unit_price": Decimal("1")}],
    )
    assert sale.total == Decimal("28000.00")


def test_offline_sale_keeps_charged_price_and_flags_it(seller, warehouse, hammer, stocked):
    sale, _ = create_sale(
        user=seller, warehouse=warehouse, client_uuid=uuid.uuid4(), offline=True,
        lines=[{"product": hammer, "quantity": 1, "unit_price": Decimal("25000")}],
    )
    assert sale.total == Decimal("25000.00")
    assert sale.lines.get().catalog_price == Decimal("28000.00")
    assert sale.needs_review


def test_offline_sale_may_leave_negative_stock(seller, warehouse, hammer, stocked):
    sale, _ = create_sale(
        user=seller, warehouse=warehouse, client_uuid=uuid.uuid4(), offline=True,
        lines=[{"product": hammer, "quantity": 12, "unit_price": Decimal("28000")}],
    )
    assert stock(hammer, warehouse) == -2
    assert sale.needs_review


def test_same_client_uuid_creates_one_sale(seller, warehouse, hammer, stocked):
    key = uuid.uuid4()
    lines = [{"product": hammer, "quantity": 1}]
    first, _ = create_sale(user=seller, warehouse=warehouse, client_uuid=key, lines=lines)
    again, created = create_sale(user=seller, warehouse=warehouse, client_uuid=key, lines=lines)
    assert not created
    assert again.pk == first.pk
    assert stock(hammer, warehouse) == 9


def test_movements_reference_sale_number(seller, warehouse, hammer, stocked):
    sale, _ = create_sale(
        user=seller, warehouse=warehouse, client_uuid=uuid.uuid4(),
        lines=[{"product": hammer, "quantity": 1}],
    )
    assert sale.lines.get().movement.reference == f"Venta {sale.number}"


def test_empty_or_zero_lines_are_rejected(seller, warehouse, hammer, stocked):
    with pytest.raises(ValidationError):
        create_sale(user=seller, warehouse=warehouse, client_uuid=uuid.uuid4(), lines=[])
    with pytest.raises(ValidationError):
        create_sale(
            user=seller, warehouse=warehouse, client_uuid=uuid.uuid4(),
            lines=[{"product": hammer, "quantity": 0}],
        )
    assert not Sale.objects.exists()


# --- API --------------------------------------------------------------------

def api(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def body(warehouse, product, **extra):
    data = {
        "client_uuid": str(uuid.uuid4()),
        "warehouse": warehouse.pk,
        "lines": [{"product": product.pk, "quantity": "1"}],
    }
    data.update(extra)
    return data


def test_cashier_creates_sale_and_retry_returns_200(seller, warehouse, hammer, stocked):
    client, data = api(seller), body(warehouse, hammer)
    res = client.post("/api/sales/", data, format="json")
    assert res.status_code == 201, res.data
    assert res.data["number"].startswith("V-")
    assert res.data["total"] == "28000.00"
    assert client.post("/api/sales/", data, format="json").status_code == 200
    assert client.get(f"/api/sales/{res.data['id']}/").data["lines"][0]["product"] == "MAR-16"
    assert stock(hammer, warehouse) == 9


def test_warehouse_assistant_cannot_sell(make_user, warehouse, hammer, stocked):
    res = api(make_user("aux", "Auxiliar de bodega")).post("/api/sales/", body(warehouse, hammer), format="json")
    assert res.status_code == 403


def test_api_rejects_sale_without_stock(seller, warehouse, hammer, stocked):
    data = body(warehouse, hammer, lines=[{"product": hammer.pk, "quantity": "99"}])
    assert api(seller).post("/api/sales/", data, format="json").status_code == 400


def test_offline_sale_requires_charged_price(seller, warehouse, hammer, stocked):
    res = api(seller).post("/api/sales/", body(warehouse, hammer, offline=True), format="json")
    assert res.status_code == 400
    assert not Sale.objects.exists()
