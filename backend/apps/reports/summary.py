"""Resumen de ingresos, gastos y ganancia (spec 013, T6). Solo lectura.

Reglas:
- Ingresos por línea (Repuestos, Taller, Lavadero) con lo cobrado, IVA incluido, como en la caja. Cada
  renglón usa la línea que guardó la venta (`SaleLine.income_line`). Una devolución resta de su línea
  en el día en que se hizo, como en el reporte de ventas.
- Costo: el de los repuestos vendidos (costo promedio con que salieron, spec 004), menos el de lo devuelto.
  Taller y lavadero no tienen costo cargado.
- Ganancia bruta = ingresos − costo; ganancia neta = bruta − gastos vigentes del período (spec 013, regla 8).
- Por día, semana (lunes a domingo) o mes. Sin `by`, lo decide el largo del período.
- Costo y ganancia solo con `reports.costs`, como Márgenes.
"""
import datetime
from collections import defaultdict

from django.utils import timezone

from apps.catalog.models import Product
from apps.expenses.models import Expense
from apps.sales.models import SaleLine, SaleReturnLine

from .services import ZERO, money, period_querysets

LINES = [Product.IncomeLine.GOODS, Product.IncomeLine.WORKSHOP, Product.IncomeLine.WASH]
GROUPS = ("day", "week", "month")


def default_group(start, end):
    days = (end - start).days + 1
    return "day" if days <= 31 else "week" if days <= 92 else "month"


def bucket(day, by):
    if by == "week":
        return day - datetime.timedelta(days=day.weekday())
    if by == "month":
        return day.replace(day=1)
    return day


def _empty():
    return {"income": defaultdict(lambda: ZERO), "cost": ZERO, "expenses": ZERO}


def summary_report(start, end, by=None, with_costs=False):
    by = by or default_group(start, end)
    sales, returns = period_querysets(start, end)
    periods = defaultdict(_empty)
    expenses_by_category = defaultdict(lambda: ZERO)

    fields = ("income_line", "total", "movement__quantity", "movement__unit_cost")
    for line in SaleLine.objects.filter(sale__in=sales).values("sale__occurred_at", *fields):
        p = periods[bucket(timezone.localdate(line["sale__occurred_at"]), by)]
        p["income"][line["income_line"]] += line["total"]
        # La salida es negativa en el kardex: -cantidad × costo es lo que costó lo vendido.
        p["cost"] += -(line["movement__quantity"] or ZERO) * (line["movement__unit_cost"] or ZERO)
    returned = SaleReturnLine.objects.filter(sale_return__in=returns).values(
        "sale_return__created_at", "sale_line__income_line", "total", "movement__quantity", "movement__unit_cost",
    )
    for line in returned:
        p = periods[bucket(timezone.localdate(line["sale_return__created_at"]), by)]
        p["income"][line["sale_line__income_line"]] -= line["total"]
        # La entrada de la devolución es positiva: resta el costo de lo que volvió.
        p["cost"] -= (line["movement__quantity"] or ZERO) * (line["movement__unit_cost"] or ZERO)

    spent = Expense.objects.filter(status=Expense.Status.ACTIVE, spent_on__range=(start, end))
    for expense in spent.values("spent_on", "amount", "category__name"):
        periods[bucket(expense["spent_on"], by)]["expenses"] += expense["amount"]
        expenses_by_category[expense["category__name"]] += expense["amount"]

    def figures(income, cost, expenses):
        total = sum((income[k] for k in LINES), ZERO)
        row = {
            "income": {k: money(income[k]) for k in LINES} | {"total": money(total)},
            "expenses": money(expenses),
            "cost": None, "gross_profit": None, "net_profit": None,
        }
        if with_costs:
            row.update(cost=money(cost), gross_profit=money(total - cost), net_profit=money(total - cost - expenses))
        return row

    rows = [{"period": key.isoformat(), **figures(p["income"], p["cost"], p["expenses"])} for key, p in sorted(periods.items())]
    all_income = defaultdict(lambda: ZERO)
    for p in periods.values():
        for k, v in p["income"].items():
            all_income[k] += v
    totals = figures(all_income, sum((p["cost"] for p in periods.values()), ZERO),
                     sum((p["expenses"] for p in periods.values()), ZERO))
    totals["expenses_by_category"] = [
        {"category": name, "amount": money(amount)} for name, amount in sorted(expenses_by_category.items(), key=lambda i: (-i[1], i[0]))
    ]
    return {"from": start.isoformat(), "to": end.isoformat(), "by": by, "with_costs": with_costs, "totals": totals, "rows": rows}

