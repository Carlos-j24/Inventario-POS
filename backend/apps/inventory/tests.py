import uuid
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.catalog.models import Unit
from apps.inventory.models import StockLevel, StockMovement
from apps.inventory.services import InsufficientStock, record_movement

pytestmark = pytest.mark.django_db
Kind = StockMovement.Kind


def stock(product, warehouse):
    return StockLevel.objects.get(product=product, warehouse=warehouse).quantity


# --- servicio ---------------------------------------------------------------

def test_receipt_adds_and_sale_subtracts(make_user, warehouse, hammer):
    user = make_user()
    record_movement(kind=Kind.RECEIPT, product=hammer, warehouse=warehouse, quantity=10, user=user, unit_cost=20000)
    mov, _ = record_movement(kind=Kind.SALE, product=hammer, warehouse=warehouse, quantity=3, user=user)
    assert stock(hammer, warehouse) == 7
    assert mov.quantity == -3
    assert mov.balance_after == 7


def test_sale_without_stock_is_rejected(make_user, warehouse, hammer):
    with pytest.raises(InsufficientStock):
        record_movement(kind=Kind.SALE, product=hammer, warehouse=warehouse, quantity=1, user=make_user())
    assert not StockMovement.objects.exists()


def test_offline_sale_may_go_negative_and_is_flagged(make_user, warehouse, hammer):
    mov, _ = record_movement(
        kind=Kind.SALE, product=hammer, warehouse=warehouse, quantity=2, user=make_user(), allow_negative=True
    )
    assert stock(hammer, warehouse) == -2
    assert mov.needs_review


def test_same_client_uuid_is_applied_once(make_user, warehouse, hammer):
    user, key = make_user(), uuid.uuid4()
    record_movement(kind=Kind.RECEIPT, product=hammer, warehouse=warehouse, quantity=5, user=user, client_uuid=key)
    _, created = record_movement(
        kind=Kind.RECEIPT, product=hammer, warehouse=warehouse, quantity=5, user=user, client_uuid=key
    )
    assert not created
    assert stock(hammer, warehouse) == 5
    assert StockMovement.objects.count() == 1


def test_receipt_by_roll_is_stored_in_meters(make_user, warehouse, cable):
    rollo = Unit.objects.get(code="rollo")
    mov, _ = record_movement(
        kind=Kind.RECEIPT, product=cable, warehouse=warehouse, quantity=2, unit=rollo,
        unit_cost=Decimal("180000"), user=make_user(),
    )
    assert stock(cable, warehouse) == 200
    assert mov.unit_cost == Decimal("1800.00")  # costo por metro


def test_fractional_sale_allowed_only_when_product_allows_it(make_user, warehouse, cable, hammer):
    user = make_user()
    record_movement(kind=Kind.RECEIPT, product=cable, warehouse=warehouse, quantity=10, user=user)
    record_movement(kind=Kind.SALE, product=cable, warehouse=warehouse, quantity=Decimal("2.5"), user=user)
    assert stock(cable, warehouse) == Decimal("7.5")

    record_movement(kind=Kind.RECEIPT, product=hammer, warehouse=warehouse, quantity=10, user=user)
    with pytest.raises(ValidationError):
        record_movement(kind=Kind.SALE, product=hammer, warehouse=warehouse, quantity=Decimal("0.5"), user=user)


def test_unknown_unit_is_rejected(make_user, warehouse, hammer):
    with pytest.raises(ValidationError):
        record_movement(
            kind=Kind.RECEIPT, product=hammer, warehouse=warehouse, quantity=1,
            unit=Unit.objects.get(code="kg"), user=make_user(),
        )


def test_adjustment_uses_sign_and_others_reject_negative(make_user, warehouse, hammer):
    user = make_user()
    record_movement(kind=Kind.RECEIPT, product=hammer, warehouse=warehouse, quantity=5, user=user)
    record_movement(kind=Kind.ADJUSTMENT, product=hammer, warehouse=warehouse, quantity=-2, user=user)
    assert stock(hammer, warehouse) == 3
    with pytest.raises(ValidationError):
        record_movement(kind=Kind.RECEIPT, product=hammer, warehouse=warehouse, quantity=-1, user=user)


# --- API --------------------------------------------------------------------

def api(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def test_warehouse_assistant_can_register_receipt(make_user, warehouse, cable):
    res = api(make_user("aux", "Auxiliar de bodega")).post(
        "/api/inventory/receipts/",
        {"product": cable.pk, "warehouse": warehouse.pk, "quantity": "1", "unit": "rollo", "unit_cost": "180000"},
        format="json",
    )
    assert res.status_code == 201, res.data
    assert res.data["quantity"] == "100.000"
    assert stock(cable, warehouse) == 100


def test_cashier_cannot_register_receipt(make_user, warehouse, cable):
    res = api(make_user("cajero", "Caja")).post(
        "/api/inventory/receipts/",
        {"product": cable.pk, "warehouse": warehouse.pk, "quantity": "1", "unit_cost": "1"},
        format="json",
    )
    assert res.status_code == 403
    assert not StockMovement.objects.exists()


def test_receipt_retry_returns_200_without_duplicating(make_user, warehouse, hammer):
    client = api(make_user("aux", "Auxiliar de bodega"))
    body = {
        "product": hammer.pk, "warehouse": warehouse.pk, "quantity": "4",
        "unit_cost": "20000", "client_uuid": str(uuid.uuid4()),
    }
    assert client.post("/api/inventory/receipts/", body, format="json").status_code == 201
    assert client.post("/api/inventory/receipts/", body, format="json").status_code == 200
    assert stock(hammer, warehouse) == 4


def test_invalid_unit_returns_400(make_user, warehouse, hammer):
    res = api(make_user("aux", "Auxiliar de bodega")).post(
        "/api/inventory/receipts/",
        {"product": hammer.pk, "warehouse": warehouse.pk, "quantity": "1", "unit": "kg", "unit_cost": "1"},
        format="json",
    )
    assert res.status_code == 400


def test_stock_list_flags_products_below_minimum(make_user, warehouse, cable):
    user = make_user("jefe", "Jefe de bodega")
    record_movement(kind=Kind.RECEIPT, product=cable, warehouse=warehouse, quantity=20, user=user)
    res = api(user).get("/api/inventory/stock/")
    assert res.status_code == 200
    assert res.data[0]["below_min"] is True


def test_kardex_lists_movements_in_order(make_user, warehouse, hammer):
    user = make_user("jefe", "Jefe de bodega")
    record_movement(kind=Kind.RECEIPT, product=hammer, warehouse=warehouse, quantity=10, user=user)
    record_movement(kind=Kind.SALE, product=hammer, warehouse=warehouse, quantity=4, user=user)
    res = api(user).get(f"/api/inventory/kardex/{hammer.pk}/")
    assert [m["balance_after"] for m in res.data] == ["10.000", "6.000"]


def test_catalog_requires_login(cable):
    assert APIClient().get("/api/catalog/products/").status_code == 403


def test_warehouses_are_listed_for_inventory_staff(make_user, warehouse):
    res = api(make_user("aux", "Auxiliar de bodega")).get("/api/inventory/warehouses/")
    assert res.data == [{"id": warehouse.pk, "code": "PRAL", "name": "Bodega principal", "is_default": False}]
    assert api(make_user("cajero", "Caja")).get("/api/inventory/warehouses/").status_code == 403
