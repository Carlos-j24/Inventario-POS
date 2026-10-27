"""Los servicios no tienen inventario (spec 010, T3)."""
import uuid
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.catalog.models import Category, Product, Unit
from apps.reports.costs import inventory_report

from .counts import products_for
from .models import StockMovement, Warehouse
from .services import record_movement

pytestmark = pytest.mark.django_db


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


def test_no_movement_can_be_recorded_for_a_service(admin, wash, warehouse):
    for kind in (StockMovement.Kind.RECEIPT, StockMovement.Kind.SALE, StockMovement.Kind.ADJUSTMENT):
        with pytest.raises(ValidationError, match="LAV-150 es un servicio"):
            record_movement(kind=kind, product=wash, warehouse=warehouse, quantity=1, user=admin)
    assert not StockMovement.objects.exists()


def test_receipts_adjustments_and_transfers_refuse_services(admin, wash, warehouse, hammer):
    client = api(admin)
    res = client.post("/api/inventory/receipts/", {"product": wash.pk, "warehouse": warehouse.pk, "quantity": "1", "unit_cost": "1"}, format="json")
    assert res.status_code == 400 and "product" in res.data
    # Un ajuste se pide sin mover nada: tiene que rechazarse al pedirlo, no al aprobarlo.
    adjustment = {"client_uuid": str(uuid.uuid4()), "warehouse": warehouse.pk, "reason": "SURPLUS", "note": "Apareció",
                  "lines": [{"product": wash.pk, "quantity": "1", "direction": "IN", "unit_cost": "1"}]}
    res = client.post("/api/inventory/adjustments/", adjustment, format="json")
    assert res.status_code == 400 and "product" in str(res.data["lines"])
    adjustment["lines"][0]["product"] = hammer.pk
    assert client.post("/api/inventory/adjustments/", {**adjustment, "client_uuid": str(uuid.uuid4())}, format="json").status_code == 201
    other = Warehouse.objects.create(code="LOC", name="Local")
    transfer = {"client_uuid": str(uuid.uuid4()), "origin": warehouse.pk, "destination": other.pk,
                "lines": [{"product": wash.pk, "quantity": "1"}]}
    res = client.post("/api/inventory/transfers/", transfer, format="json")
    assert res.status_code == 400 and "LAV-150 es un servicio" in str(res.data)
    # Un producto sí entra (la prueba no está rechazando todo).
    res = client.post("/api/inventory/receipts/", {"product": hammer.pk, "warehouse": warehouse.pk, "quantity": "1", "unit_cost": "1"}, format="json")
    assert res.status_code == 201, res.data


def test_counts_and_the_valued_inventory_leave_services_out(wash, hammer, warehouse):
    assert list(products_for(warehouse)) == [hammer]
    assert [r["sku"] for r in inventory_report()["rows"]] == ["MAR-16"]
