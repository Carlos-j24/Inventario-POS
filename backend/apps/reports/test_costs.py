"""Inventario valorizado, márgenes y arqueos (spec 004, T3)."""
import datetime
import uuid
from decimal import Decimal

import pytest

from apps.cash.models import CashRegister, Shift
from apps.cash.services import close_shift, open_shift
from apps.catalog.models import Category, Product, Unit
from apps.inventory.models import StockMovement, Warehouse
from apps.inventory.services import record_movement
from apps.sales.models import SaleReturn
from apps.sales.returns import create_return, void_sale

from .tests import DAY1, DAY2, at, get, sell

pytestmark = pytest.mark.django_db

RECEIPT = StockMovement.Kind.RECEIPT


def make_product(sku, name, unit="und", **extra):
    return Product.objects.create(
        sku=sku, name=name, category=Category.objects.get_or_create(name="Varios")[0],
        base_unit=Unit.objects.get(code=unit), sale_price=Decimal("8000"), **extra,
    )


@pytest.fixture
def world(make_user, warehouse, shift, hammer, cable):
    cashier = make_user("caja1", "Caja")
    supervisor = make_user("super", "Supervisor")
    admin = make_user("jefe", "Administrador")
    wire = make_product("ALA-18", "Alambre negro 18", unit="kg", min_stock=Decimal("10"))
    screw = make_product("TOR-1/4", "Tornillo 1/4")
    make_product("VIEJO", "Producto descontinuado", is_active=False)

    def receive(product, qty, cost):
        record_movement(kind=RECEIPT, product=product, warehouse=warehouse, quantity=qty, user=cashier, unit_cost=cost)

    # Criterio de la spec: 10 a $1.000 y 10 a $2.000 dejan el costo en $1.500.
    receive(hammer, 10, "1000")
    receive(hammer, 10, "2000")
    receive(cable, 300, "1800")
    receive(wire, 5, "6000")
    record_movement(kind=StockMovement.Kind.ADJUSTMENT, product=screw, warehouse=warehouse, quantity=-2,
                    user=cashier, allow_negative=True)

    s1 = sell(cashier, shift, hammer, "5", [{"method": "CASH", "amount": "140000"}], at(DAY1, 9))
    sell(cashier, shift, cable, "10", [{"method": "CARD", "amount": "32000"}], at(DAY1, 10))
    voided = sell(cashier, shift, wire, "1", [{"method": "CASH", "amount": "8000"}], at(DAY1, 11))
    void_sale(sale=voided, user=supervisor, reason="Error")
    # Entra mercancía más cara después de vender: el costo de la venta no cambia.
    receive(hammer, 10, "3000")

    register2 = CashRegister.objects.create(code="CAJA2", name="Caja 2", warehouse=warehouse)
    shift2 = open_shift(register=register2, user=supervisor, opening_float=Decimal("50000"))
    ret, _ = create_return(
        sale=s1, user=supervisor, shift=shift2, lines=[{"sale_line": s1.lines.get(), "quantity": "1"}],
        refund_method="CASH", reason="Defectuoso", client_uuid=uuid.uuid4(),
    )
    SaleReturn.objects.filter(pk=ret.pk).update(created_at=at(DAY2, 15))

    close_shift(shift=shift, user=cashier, counted_cash=Decimal("238000"), notes="Faltan 2.000")
    close_shift(shift=shift2, user=supervisor, counted_cash=Decimal("22500"))
    Shift.objects.filter(pk=shift.pk).update(closed_at=at(DAY1, 22))
    Shift.objects.filter(pk=shift2.pk).update(closed_at=at(DAY2, 18))
    open_shift(register=register2, user=supervisor, opening_float=Decimal("0"))  # abierto: no sale
    return {"cashier": cashier, "supervisor": supervisor, "admin": admin, "register2": register2, "s1": s1}


def report(world, name, **params):
    res = get(world["admin"], f"/api/reports/{name}/", **params)
    assert res.status_code == 200, res.data
    return res.data


PERIOD = {"from": "2026-10-01", "to": "2026-10-02"}


# --- márgenes ---------------------------------------------------------------

def test_sale_keeps_its_cost_when_later_receipts_change_the_average(world):
    movement = world["s1"].lines.get().movement
    movement.refresh_from_db()
    assert movement.unit_cost == Decimal("1500.0000")
    data = report(world, "margins", **{"from": "2026-10-01"})
    hammer = next(r for r in data["rows"] if r["sku"] == "MAR-16")
    assert (hammer["net_sales"], hammer["cost"]) == ("117647.06", "7500.00")


def test_margins_by_product_and_total(world):
    data = report(world, "margins", **PERIOD)
    assert data["rows"] == [
        {"product": data["rows"][0]["product"], "sku": "MAR-16", "name": "Martillo 16 oz", "is_service": False,
         "net_sales": "94117.65", "cost": "6000.00", "margin": "88117.65", "margin_pct": "93.6", "cost_estimated": False},
        {"product": data["rows"][1]["product"], "sku": "CAB-12", "name": "Cable THHN calibre 12", "is_service": False,
         "net_sales": "26890.76", "cost": "18000.00", "margin": "8890.76", "margin_pct": "33.1", "cost_estimated": False},
    ]
    assert data["totals"] == {
        "net_sales": "121008.41", "cost": "24000.00", "margin": "97008.41", "margin_pct": "80.2", "cost_estimated": False,
        "services_net_sales": "0.00",
    }


def test_return_subtracts_margin_on_the_day_it_was_made(world):
    data = report(world, "margins", **{"from": "2026-10-02"})
    assert [(r["sku"], r["net_sales"], r["cost"], r["margin"]) for r in data["rows"]] == [
        ("MAR-16", "-23529.41", "-1500.00", "-22029.41"),
    ]
    by_register = report(world, "margins", **PERIOD, register=world["register2"].pk)
    assert by_register["totals"]["margin"] == "-22029.41"


def test_estimated_costs_are_flagged(world):
    StockMovement.objects.filter(pk=world["s1"].lines.get().movement_id).update(cost_estimated=True)
    data = report(world, "margins", **PERIOD)
    assert [r["cost_estimated"] for r in data["rows"]] == [True, False]
    assert data["totals"]["cost_estimated"] is True


def test_sale_without_saved_cost_counts_zero_and_is_flagged(world):
    StockMovement.objects.filter(kind=StockMovement.Kind.SALE, product__sku="CAB-12").update(unit_cost=None)
    cable = next(r for r in report(world, "margins", **PERIOD)["rows"] if r["sku"] == "CAB-12")
    assert (cable["cost"], cable["margin"], cable["cost_estimated"]) == ("0.00", "26890.76", True)


def test_empty_margins_have_no_percentage(world):
    data = report(world, "margins", **{"from": "2026-09-01"})
    assert data["totals"] == {"net_sales": "0.00", "cost": "0.00", "margin": "0.00", "margin_pct": None, "cost_estimated": False,
                             "services_net_sales": "0.00"}
    assert data["rows"] == []


# --- inventario valorizado --------------------------------------------------

def test_inventory_valued_at_average_cost(world):
    data = report(world, "inventory")
    rows = {r["sku"]: r for r in data["rows"]}
    assert list(rows) == ["ALA-18", "CAB-12", "MAR-16", "TOR-1/4"]  # el inactivo sin existencias no sale
    # Martillo: 15 a 1.500 + 10 a 3.000 → 2.100; vuelve 1 a 1.500 → (25 × 2.100 + 1.500) ÷ 26.
    assert rows["MAR-16"] | {"product": 0} == {
        "product": 0, "sku": "MAR-16", "name": "Martillo 16 oz", "unit": "und", "stock": "26.000", "min_stock": "0.000",
        "average_cost": "2076.9231", "value": "54000.00", "below_min": False, "negative": False,
    }
    assert (rows["CAB-12"]["stock"], rows["CAB-12"]["value"], rows["CAB-12"]["below_min"]) == ("290.000", "522000.00", False)
    assert (rows["ALA-18"]["stock"], rows["ALA-18"]["value"], rows["ALA-18"]["below_min"]) == ("5.000", "30000.00", True)
    # Existencias negativas: se marcan y valen 0.
    assert (rows["TOR-1/4"]["stock"], rows["TOR-1/4"]["value"], rows["TOR-1/4"]["average_cost"]) == ("-2.000", "0.00", None)
    assert (rows["TOR-1/4"]["negative"], rows["TOR-1/4"]["below_min"]) == (True, False)
    assert data["totals"] == {"value": "606000.00", "products": 4, "below_min": 1, "negative": 1}


def test_inactive_product_with_stock_still_counts(world, warehouse):
    old = Product.objects.get(sku="VIEJO")
    record_movement(kind=RECEIPT, product=old, warehouse=warehouse, quantity=3, user=world["cashier"], unit_cost="100")
    rows = {r["sku"]: r for r in report(world, "inventory")["rows"]}
    assert rows["VIEJO"]["value"] == "300.00"
    # Cuando se le acaban las existencias, el inactivo deja de salir.
    record_movement(kind=StockMovement.Kind.ADJUSTMENT, product=old, warehouse=warehouse, quantity=-3, user=world["cashier"])
    assert "VIEJO" not in [r["sku"] for r in report(world, "inventory")["rows"]]


def test_inventory_by_warehouse(world, hammer):
    other = Warehouse.objects.create(code="SUR", name="Bodega sur")
    record_movement(kind=RECEIPT, product=hammer, warehouse=other, quantity=2, user=world["cashier"], unit_cost="4000")
    rows = {r["sku"]: r for r in report(world, "inventory", warehouse=other.pk)["rows"]}
    assert (rows["MAR-16"]["stock"], rows["MAR-16"]["value"]) == ("2.000", "8000.00")
    assert rows["CAB-12"]["value"] == "0.00"
    everywhere = {r["sku"]: r for r in report(world, "inventory")["rows"]}["MAR-16"]
    assert (everywhere["stock"], everywhere["value"], everywhere["average_cost"]) == ("28.000", "62000.00", "2214.2857")


# --- arqueos ----------------------------------------------------------------

def test_shifts_report(world):
    data = report(world, "shifts", **PERIOD)
    first, second = data["rows"]
    assert (first["register"], first["opened_by"], first["closed_by"], first["sales_count"]) == ("CAJA1", "apertura", "caja1", 2)
    assert first["by_method"] == {"CASH": "140000.00", "CARD": "32000.00", "TRANSFER": "0.00"}
    assert (first["opening_float"], first["expected_cash"], first["counted_cash"], first["difference"]) == (
        "100000.00", "240000.00", "238000.00", "-2000.00",
    )
    assert first["notes"] == "Faltan 2.000"
    assert (second["register"], second["by_method"]["CASH"], second["expected_cash"], second["difference"]) == (
        "CAJA2", "-28000.00", "22000.00", "500.00",
    )
    assert data["totals"] == {
        "shifts": 2, "expected_cash": "262000.00", "counted_cash": "260500.00", "difference": "-1500.00",
        "shortage": "2000.00", "overage": "500.00",
        "by_method": {"CASH": "112000.00", "CARD": "32000.00", "TRANSFER": "0.00"},
    }


def test_shifts_by_closing_day_and_register(world):
    day2 = report(world, "shifts", **{"from": "2026-10-02"})
    assert [r["register"] for r in day2["rows"]] == ["CAJA2"]
    assert (day2["totals"]["shortage"], day2["totals"]["overage"]) == ("0.00", "500.00")
    only1 = report(world, "shifts", **PERIOD, register=Shift.objects.get(closed_at=at(DAY1, 22)).register_id)
    assert [r["register"] for r in only1["rows"]] == ["CAJA1"]
    assert report(world, "shifts", **{"from": "2026-10-03"})["totals"]["shifts"] == 0


def test_shift_closed_at_night_counts_on_its_business_day(world):
    Shift.objects.filter(closed_at=at(DAY2, 18)).update(closed_at=at(DAY2, 23) + datetime.timedelta(minutes=30))
    assert report(world, "shifts", **{"from": "2026-10-02"})["totals"]["shifts"] == 1


# --- permisos ---------------------------------------------------------------

@pytest.mark.parametrize("name", ["inventory", "margins"])
def test_costs_need_reports_costs(world, name):
    assert get(world["supervisor"], f"/api/reports/{name}/").status_code == 403
    assert get(world["admin"], f"/api/reports/{name}/").status_code == 200


def test_shifts_need_reports_view(world):
    assert get(world["cashier"], "/api/reports/shifts/").status_code == 403
    assert get(world["supervisor"], "/api/reports/shifts/").status_code == 200
