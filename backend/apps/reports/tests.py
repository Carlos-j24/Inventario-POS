import datetime
import uuid
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from rest_framework.test import APIClient

from apps.cash.models import CashRegister
from apps.cash.services import open_shift
from apps.catalog.models import Category, Product, Unit
from apps.inventory.models import StockMovement
from apps.inventory.services import record_movement
from apps.sales.models import Sale, SaleReturn, business_date
from apps.sales.returns import create_return, void_sale
from apps.sales.services import create_sale

pytestmark = pytest.mark.django_db

BOGOTA = ZoneInfo("America/Bogota")
DAY1, DAY2 = datetime.date(2026, 10, 1), datetime.date(2026, 10, 2)


def at(day, hour):
    return datetime.datetime(day.year, day.month, day.day, hour, 0, tzinfo=BOGOTA)


def sell(user, shift, product, quantity, payments, when):
    sale, _ = create_sale(
        user=user, shift=shift, client_uuid=uuid.uuid4(),
        lines=[{"product": product, "quantity": Decimal(quantity)}], payments=payments,
    )
    Sale.objects.filter(pk=sale.pk).update(occurred_at=when)
    sale.refresh_from_db()
    return sale


@pytest.fixture
def wire(db):
    return Product.objects.create(
        sku="ALA-18", name="Alambre negro 18", category=Category.objects.create(name="Ferretería"),
        base_unit=Unit.objects.get(code="kg"), sale_price=Decimal("8000"), allows_fractions=True,
    )


@pytest.fixture
def world(make_user, warehouse, register, shift, hammer, cable, wire):
    """Dos días, dos cajas, un vendedor por pedido, una venta anulada y una devolución al día siguiente."""
    cashier = make_user("caja1", "Caja")
    seller = make_user("vende1", "Ventas")
    supervisor = make_user("super", "Supervisor")
    for product, qty in ((hammer, 10), (cable, 300), (wire, 5)):
        record_movement(kind=StockMovement.Kind.RECEIPT, product=product, warehouse=warehouse, quantity=qty, user=cashier)
    register2 = CashRegister.objects.create(code="CAJA2", name="Caja 2", warehouse=warehouse)
    shift2 = open_shift(register=register2, user=cashier, opening_float=Decimal("0"))

    s1 = sell(cashier, shift, hammer, "2", [{"method": "CASH", "amount": "56000"}], at(DAY1, 9))
    # 21:30 en Bogotá ya es el día siguiente en UTC: debe contar el día 1.
    s2 = sell(cashier, shift, cable, "10", [{"method": "CARD", "amount": "20000"}, {"method": "CASH", "amount": "12000"}], at(DAY1, 21))
    Sale.objects.filter(pk=s2.pk).update(occurred_at=at(DAY1, 21) + datetime.timedelta(minutes=30))
    s3 = sell(cashier, shift2, hammer, "1", [{"method": "TRANSFER", "amount": "28000"}], at(DAY2, 10))
    Sale.objects.filter(pk=s3.pk).update(salesperson=seller)
    voided = sell(cashier, shift, wire, "1", [{"method": "CASH", "amount": "8000"}], at(DAY1, 11))
    void_sale(sale=voided, user=supervisor, reason="Error de digitación")

    # Devolución de un martillo de s1, hecha el día 2 desde la caja 2.
    ret, _ = create_return(
        sale=s1, user=supervisor, shift=shift2, lines=[{"sale_line": s1.lines.get(), "quantity": "1"}],
        refund_method="CASH", reason="Defectuoso", client_uuid=uuid.uuid4(),
    )
    SaleReturn.objects.filter(pk=ret.pk).update(created_at=at(DAY2, 15))
    return {"supervisor": supervisor, "cashier": cashier, "seller": seller, "register2": register2}


def get(user, url, **params):
    client = APIClient()
    client.force_authenticate(user)
    return client.get(url, params)


def sales(world, **params):
    res = get(world["supervisor"], "/api/reports/sales/", **params)
    assert res.status_code == 200, res.data
    return res.data


def products(world, **params):
    res = get(world["supervisor"], "/api/reports/products/", **params)
    assert res.status_code == 200, res.data
    return res.data


# --- ventas -----------------------------------------------------------------

def test_sales_totals_are_net_of_voids_and_returns(world):
    data = sales(world, **{"from": "2026-10-01", "to": "2026-10-02"})
    t = data["totals"]  # todo con IVA del 19 %
    assert (data["from"], data["to"]) == ("2026-10-01", "2026-10-02")
    assert t["sales_count"] == 3
    assert t["total"] == "116000.00"
    assert t["subtotal"] == "97478.99"
    assert t["tax"] == "18521.01"
    assert (t["returns_total"], t["returns_subtotal"], t["returns_tax"]) == ("28000.00", "23529.41", "4470.59")
    assert t["net_total"] == "88000.00"
    assert t["net_subtotal"] == "73949.58"
    assert t["net_tax"] == "14050.42"
    assert t["average_ticket"] == "38666.67"


def test_sales_by_day_return_subtracts_on_the_day_it_was_made(world):
    data = sales(world, **{"from": "2026-10-01", "to": "2026-10-02"})
    assert data["by_day"] == [
        {"day": "2026-10-01", "sales_count": 2, "total": "88000.00", "returns": "0.00", "net": "88000.00"},
        {"day": "2026-10-02", "sales_count": 1, "total": "28000.00", "returns": "28000.00", "net": "0.00"},
    ]


def test_single_day_periods(world):
    day1 = sales(world, **{"from": "2026-10-01"})
    assert (day1["to"], day1["totals"]["sales_count"], day1["totals"]["net_total"]) == ("2026-10-01", 2, "88000.00")
    assert day1["totals"]["returns_total"] == "0.00"
    day2 = sales(world, **{"from": "2026-10-02", "to": "2026-10-02"})
    assert (day2["totals"]["total"], day2["totals"]["returns_total"], day2["totals"]["net_total"]) == (
        "28000.00", "28000.00", "0.00",
    )
    # El día 2 caja1 no vendió, pero se le devolvió una venta; y el efectivo solo tuvo reembolso.
    assert day2["by_salesperson"][0] == {
        "salesperson": "caja1", "sales_count": 0, "total": "0.00", "returns": "28000.00", "net": "-28000.00",
    }
    assert day2["by_method"][0] == {
        "method": "CASH", "label": "Efectivo", "payments": "0.00", "refunds": "28000.00", "net": "-28000.00",
    }


def test_sales_by_register_counts_refund_where_the_money_left(world):
    data = sales(world, **{"from": "2026-10-01", "to": "2026-10-02"})
    assert data["by_register"] == [
        {"register": "CAJA1", "sales_count": 2, "total": "88000.00", "returns": "0.00", "net": "88000.00"},
        {"register": "CAJA2", "sales_count": 1, "total": "28000.00", "returns": "28000.00", "net": "0.00"},
    ]
    only2 = sales(world, **{"from": "2026-10-01", "to": "2026-10-02", "register": world["register2"].pk})
    assert (only2["totals"]["total"], only2["totals"]["returns_total"]) == ("28000.00", "28000.00")


def test_sales_by_salesperson_returns_go_to_who_sold(world):
    data = sales(world, **{"from": "2026-10-01", "to": "2026-10-02"})
    assert data["by_salesperson"] == [
        {"salesperson": "caja1", "sales_count": 2, "total": "88000.00", "returns": "28000.00", "net": "60000.00"},
        {"salesperson": "vende1", "sales_count": 1, "total": "28000.00", "returns": "0.00", "net": "28000.00"},
    ]
    only = sales(world, **{"from": "2026-10-01", "to": "2026-10-02", "salesperson": world["seller"].pk})
    assert (only["totals"]["sales_count"], only["totals"]["returns_total"]) == (1, "0.00")


def test_sales_by_payment_method(world):
    data = sales(world, **{"from": "2026-10-01", "to": "2026-10-02"})
    assert data["by_method"] == [
        {"method": "CASH", "label": "Efectivo", "payments": "68000.00", "refunds": "28000.00", "net": "40000.00"},
        {"method": "CARD", "label": "Tarjeta", "payments": "20000.00", "refunds": "0.00", "net": "20000.00"},
        {"method": "TRANSFER", "label": "Transferencia", "payments": "28000.00", "refunds": "0.00", "net": "28000.00"},
    ]


def test_empty_period_and_default_is_today(world):
    data = sales(world)
    assert data["from"] == data["to"] == business_date().isoformat()
    assert data["totals"]["sales_count"] == 0
    assert data["totals"]["average_ticket"] == "0.00"
    assert data["by_day"] == data["by_method"] == []


# --- productos --------------------------------------------------------------

def test_products_ranking_net_of_returns(world):
    data = products(world, **{"from": "2026-10-01", "to": "2026-10-02"})
    hammer = {"sku": "MAR-16", "unit": "und", "sales_count": 2, "quantity": "2.000", "total": "56000.00", "subtotal": "47058.82"}
    cable = {"sku": "CAB-12", "unit": "m", "sales_count": 1, "quantity": "10.000", "total": "32000.00", "subtotal": "26890.76"}
    assert [{k: row[k] for k in hammer} for row in data["by_quantity"]] == [cable, hammer]
    assert [{k: row[k] for k in hammer} for row in data["by_value"]] == [hammer, cable]
    assert data["by_value"][0]["name"] == "Martillo 16 oz"


def test_same_product_twice_in_a_sale_counts_one_sale(world, shift, hammer):
    sale, _ = create_sale(
        user=world["cashier"], shift=shift, client_uuid=uuid.uuid4(),
        lines=[{"product": hammer, "quantity": Decimal("1")}, {"product": hammer, "quantity": Decimal("1")}],
        payments=[{"method": "CASH", "amount": "56000"}],
    )
    row = next(r for r in products(world)["by_value"] if r["sku"] == "MAR-16")
    assert (row["sales_count"], row["quantity"], row["total"]) == (1, "2.000", "56000.00")


def test_products_limit(world):
    data = products(world, **{"from": "2026-10-01", "to": "2026-10-02", "limit": "1"})
    assert [r["sku"] for r in data["by_quantity"]] == ["CAB-12"]
    assert [r["sku"] for r in data["by_value"]] == ["MAR-16"]
    data = products(world, **{"from": "2026-10-01", "to": "2026-10-02", "limit": "nada"})
    assert len(data["by_value"]) == 2


def test_return_of_a_sale_from_another_period_subtracts(world):
    data = products(world, **{"from": "2026-10-02"})
    row = next(r for r in data["by_value"] if r["sku"] == "MAR-16")
    assert (row["quantity"], row["total"], row["sales_count"]) == ("0.000", "0.00", 1)


def test_not_moved_lists_products_without_valid_sales(world):
    data = products(world, **{"from": "2026-10-01", "to": "2026-10-02"})
    # El alambre solo tuvo una venta anulada: cuenta como sin movimiento y su stock volvió.
    assert data["not_moved"] == [
        {"product": Product.objects.get(sku="ALA-18").pk, "sku": "ALA-18", "name": "Alambre negro 18", "unit": "kg", "stock": "5.000"},
    ]
    Product.objects.filter(sku="ALA-18").update(is_active=False)
    assert products(world, **{"from": "2026-10-01"})["not_moved"] == []


def test_products_by_register(world):
    data = products(world, **{"from": "2026-10-01", "to": "2026-10-02", "register": world["register2"].pk})
    # Caja 2: vendió un martillo y reembolsó otro.
    assert [(r["sku"], r["quantity"], r["total"]) for r in data["by_value"]] == [("MAR-16", "0.000", "0.00")]
    assert [r["sku"] for r in data["not_moved"]] == ["ALA-18", "CAB-12"]


# --- permisos y período ----------------------------------------------------

@pytest.mark.parametrize("url", ["/api/reports/sales/", "/api/reports/products/"])
def test_reports_require_permission(world, url):
    assert get(world["cashier"], url).status_code == 403
    assert APIClient().get(url).status_code == 403
    assert get(world["supervisor"], url).status_code == 200


@pytest.mark.parametrize("params", [
    {"from": "01/10/2026"},
    {"from": "2026-10-01", "to": "2026-13-01"},
    {"from": "2026-10-02", "to": "2026-10-01"},
    {"from": "2025-09-30", "to": "2026-10-01"},
])
def test_invalid_periods(world, params):
    res = get(world["supervisor"], "/api/reports/sales/", **params)
    assert res.status_code == 400
    assert "period" in res.data


def test_a_full_year_is_allowed(world):
    data = sales(world, **{"from": "2025-10-01", "to": "2026-10-01"})
    assert data["totals"]["sales_count"] == 2
