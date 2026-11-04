"""Resumen de ingresos, gastos y ganancia (spec 013, T6)."""
import datetime
import uuid
from decimal import Decimal

import pytest

from apps.catalog.models import Category, Product, Unit
from apps.expenses.models import ExpenseCategory
from apps.expenses.services import create_expense, void_expense
from apps.inventory.models import StockMovement
from apps.inventory.services import record_movement
from apps.sales.models import Sale, SaleReturn
from apps.sales.returns import create_return
from apps.sales.services import create_sale

from .summary import bucket, default_group
from .tests import at, get

pytestmark = pytest.mark.django_db
D = Decimal
THU, MON = datetime.date(2026, 10, 1), datetime.date(2026, 10, 5)  # semanas distintas


def product(sku, price, **extra):
    return Product.objects.create(
        sku=sku, name=sku, category=Category.objects.get_or_create(name="Varios")[0],
        base_unit=Unit.objects.get(code="und"), sale_price=D(price), **extra,
    )


def sell(user, shift, items, when):
    total = sum(p.sale_price * q for p, q in items)
    sale, _ = create_sale(user=user, shift=shift, client_uuid=uuid.uuid4(),
                          lines=[{"product": p, "quantity": D(q)} for p, q in items],
                          payments=[{"method": "CASH", "amount": str(total)}])
    Sale.objects.filter(pk=sale.pk).update(occurred_at=when)
    return sale


@pytest.fixture
def world(make_user, warehouse, shift):
    owner = make_user("dueno", "Administrador")
    oil = product("ACE", "40000")
    record_movement(kind=StockMovement.Kind.RECEIPT, product=oil, warehouse=warehouse, quantity=10, user=owner, unit_cost="28000")
    labor = product("MO", "20000", is_service=True)  # Taller por defecto
    wash = product("LAV", "12000", is_service=True, income_line="WASH")
    # El ejemplo de la spec: un día con aceite, mano de obra y dos lavados, y $15.000 de jabón.
    sell(owner, shift, [(oil, 1), (labor, 1)], at(THU, 9))
    sell(owner, shift, [(wash, 2)], at(THU, 11))
    soap = ExpenseCategory.objects.get(name="Insumos")
    create_expense(user=owner, spent_on=THU, amount=D("15000"), category=soap)
    # Otra semana: dos aceites y un lavado; se devuelven un aceite (vuelve con su costo) y el lavado, y se paga el arriendo.
    later = sell(owner, shift, [(oil, 2), (wash, 1)], at(MON, 10))
    ret, _ = create_return(sale=later, user=owner, shift=shift, lines=[
        {"sale_line": later.lines.get(product=wash), "quantity": "1"}, {"sale_line": later.lines.get(product=oil), "quantity": "1"},
    ], refund_method="CASH", reason="No le gustó", client_uuid=uuid.uuid4())
    SaleReturn.objects.filter(pk=ret.pk).update(created_at=at(MON, 16))
    create_expense(user=owner, spent_on=MON, amount=D("500000"), category=ExpenseCategory.objects.get(name="Arriendo"))
    voided = create_expense(user=owner, spent_on=MON, amount=D("999"), category=soap)
    void_expense(user=owner, expense=voided, reason="Repetido")
    return {"owner": owner, "supervisor": make_user("super", "Supervisor")}


def summary(user, **params):
    res = get(user, "/api/reports/summary/", **params)
    assert res.status_code == 200, res.data
    return res.data


def test_one_day_as_in_the_spec(world):
    data = summary(world["owner"], **{"from": "2026-10-01", "to": "2026-10-01"})
    assert data["by"] == "day"
    day = data["totals"]
    assert day["income"] == {"GOODS": "40000.00", "WORKSHOP": "20000.00", "WASH": "24000.00", "total": "84000.00"}
    assert (day["cost"], day["gross_profit"], day["expenses"], day["net_profit"]) == ("28000.00", "56000.00", "15000.00", "41000.00")
    assert day["expenses_by_category"] == [{"category": "Insumos", "amount": "15000.00"}]
    assert [r["period"] for r in data["rows"]] == ["2026-10-01"]


def test_a_return_subtracts_from_its_line_on_its_day_and_voided_expenses_do_not_count(world):
    data = summary(world["owner"], **{"from": "2026-10-05", "to": "2026-10-05"})
    day = data["totals"]
    assert day["income"] == {"GOODS": "40000.00", "WORKSHOP": "0.00", "WASH": "0.00", "total": "40000.00"}
    assert (day["cost"], day["gross_profit"], day["expenses"], day["net_profit"]) == ("28000.00", "12000.00", "500000.00", "-488000.00")


def test_by_week_monday_to_sunday_and_by_month(world):
    period = {"from": "2026-10-01", "to": "2026-10-05"}
    weeks = summary(world["owner"], by="week", **period)
    assert [(r["period"], r["income"]["total"], r["net_profit"]) for r in weeks["rows"]] == [
        ("2026-09-28", "84000.00", "41000.00"), ("2026-10-05", "40000.00", "-488000.00"),
    ]
    month = summary(world["owner"], by="month", **period)
    assert [(r["period"], r["income"]["total"], r["cost"], r["expenses"]) for r in month["rows"]] == [
        ("2026-10-01", "124000.00", "56000.00", "515000.00"),
    ]
    assert month["totals"]["expenses_by_category"] == [
        {"category": "Arriendo", "amount": "500000.00"}, {"category": "Insumos", "amount": "15000.00"},
    ]


def test_without_reports_costs_there_is_no_cost_nor_profit(world):
    assert not world["supervisor"].has_app_permission("reports.costs")
    data = summary(world["supervisor"], **{"from": "2026-10-01", "to": "2026-10-01"})
    assert data["with_costs"] is False
    assert (data["totals"]["cost"], data["totals"]["gross_profit"], data["totals"]["net_profit"]) == (None, None, None)
    assert data["totals"]["income"]["total"] == "84000.00" and data["totals"]["expenses"] == "15000.00"
    assert data["rows"][0]["net_profit"] is None


def test_grouping_by_default_and_wrong_values(world):
    assert default_group(THU, THU) == "day"
    assert default_group(THU, THU + datetime.timedelta(days=30)) == "day"
    assert default_group(THU, THU + datetime.timedelta(days=31)) == "week"
    assert default_group(THU, THU + datetime.timedelta(days=91)) == "week"
    assert default_group(THU, THU + datetime.timedelta(days=92)) == "month"
    assert bucket(datetime.date(2026, 10, 4), "week") == datetime.date(2026, 9, 28)  # domingo: su lunes
    assert bucket(MON, "week") == MON
    assert get(world["owner"], "/api/reports/summary/", by="year").status_code == 400
    assert get(world["owner"], "/api/reports/summary/").data["by"] == "day"
    assert summary(world["owner"], **{"from": "2026-09-01", "to": "2026-10-05"})["by"] == "week"  # 35 días


def test_the_summary_needs_reports_view(world, make_user):
    assert get(make_user("laura", "Caja"), "/api/reports/summary/").status_code == 403
