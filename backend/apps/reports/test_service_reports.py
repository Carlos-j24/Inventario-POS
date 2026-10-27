"""Servicios en los reportes (spec 010, T3): cantidad desde la línea y márgenes aparte."""
import uuid
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.catalog.models import Category, Product, Unit
from apps.inventory.models import StockMovement
from apps.inventory.services import record_movement
from apps.sales.returns import create_return
from apps.sales.services import create_sale

pytestmark = pytest.mark.django_db
D = Decimal


@pytest.fixture
def admin(make_user):
    return make_user("dueno", "Administrador")


@pytest.fixture
def world(admin, shift, warehouse, hammer):
    """Hoy: 3 lavados ($12.000) y 2 aceites ($30.000, costo $20.000); se devuelve un lavado y un aceite."""
    wash = Product.objects.create(
        sku="LAV-150", name="Lavado moto hasta 150 cc", category=Category.objects.create(name="Lavadero"),
        base_unit=Unit.objects.get(code="und"), sale_price=D("12000"), is_service=True,
    )
    oil = Product.objects.create(
        sku="ACE-20W50", name="Aceite 20W50", category=Category.objects.create(name="Lubricantes"),
        base_unit=Unit.objects.get(code="und"), sale_price=D("30000"),
    )
    record_movement(kind=StockMovement.Kind.RECEIPT, product=oil, warehouse=warehouse, quantity=5, user=admin, unit_cost="20000")
    sale, _ = create_sale(user=admin, shift=shift, client_uuid=uuid.uuid4(),
                          lines=[{"product": wash, "quantity": 3}, {"product": oil, "quantity": 2}],
                          payments=[{"method": "CASH", "amount": D("96000")}])
    create_return(sale=sale, user=admin, shift=shift, refund_method="CASH", reason="No se lavó", client_uuid=uuid.uuid4(),
                  lines=[{"sale_line": sale.lines.get(product=wash), "quantity": 1}, {"sale_line": sale.lines.get(product=oil), "quantity": 1}])
    return {"wash": wash, "oil": oil}


def report(user, name):
    today = timezone.localdate().isoformat()
    client = APIClient()
    client.force_authenticate(user)
    res = client.get(f"/api/reports/{name}/", {"from": today, "to": today})
    assert res.status_code == 200, res.data
    return res.data


def test_products_report_counts_services_from_the_line(admin, world):
    Product.objects.create(sku="LAV-AC", name="Lavado alto cilindraje", category=world["wash"].category,
                           base_unit=world["wash"].base_unit, sale_price=D("18000"), is_service=True)  # sin ventas
    data = report(admin, "products")
    rows = {r["sku"]: (r["quantity"], r["total"]) for r in data["by_quantity"]}
    assert rows == {"LAV-150": ("2.000", "24000.00"), "ACE-20W50": ("1.000", "30000.00")}
    assert [r["sku"] for r in data["not_moved"]] == ["MAR-16"]  # un servicio sin ventas no es mercancía quieta


def test_margins_keep_services_apart_and_without_cost(admin, world):
    data = report(admin, "margins")
    oil, wash = data["rows"]  # la mercancía primero
    assert (oil["sku"], oil["is_service"], oil["cost"], oil["margin"]) == ("ACE-20W50", False, "20000.00", "5210.09")
    assert (wash["sku"], wash["is_service"], wash["net_sales"], wash["cost"], wash["margin"], wash["margin_pct"], wash["cost_estimated"]) == (
        "LAV-150", True, "20168.07", "0.00", "20168.07", "100.0", False,
    )
    totals = data["totals"]
    assert (totals["net_sales"], totals["cost"], totals["margin"], totals["margin_pct"]) == ("25210.09", "20000.00", "5210.09", "20.7")
    assert (totals["services_net_sales"], totals["cost_estimated"]) == ("20168.07", False)


def test_margins_without_services_say_zero(admin, shift, warehouse, hammer):
    record_movement(kind=StockMovement.Kind.RECEIPT, product=hammer, warehouse=warehouse, quantity=1, user=admin, unit_cost="20000")
    create_sale(user=admin, shift=shift, client_uuid=uuid.uuid4(), lines=[{"product": hammer, "quantity": 1}],
                payments=[{"method": "CASH", "amount": D("28000")}])
    totals = report(admin, "margins")["totals"]
    assert (totals["services_net_sales"], totals["cost"]) == ("0.00", "20000.00")
