"""Reportes de ventas y productos (spec 004, T2). Solo lectura.

Reglas:
- Una venta cuenta en el día en que ocurrió (occurred_at, hora de Bogotá); las anuladas no cuentan.
- Una devolución resta en el día en que se hizo (created_at), no en el de la venta: ese día salió el
  dinero, así cuadra con los arqueos. Por caja cuenta la caja de donde salió el reembolso; por
  vendedor, quien hizo la venta.
- El dinero va como texto con 2 decimales y las cantidades con 3 (nunca float).
"""
from decimal import Decimal

from django.db.models import Count, F, Sum
from django.db.models.functions import Coalesce, TruncDate

from apps.cash.models import Payment, Refund
from apps.catalog.models import Product
from apps.inventory.models import StockLevel
from apps.sales.models import Sale, SaleLine, SaleReturn, SaleReturnLine

ZERO = Decimal(0)


def money(value):
    return str((value or ZERO).quantize(Decimal("0.01")))


def qty(value):
    return str((value or ZERO).quantize(Decimal("0.001")))


def period_querysets(start, end, register=None, salesperson=None):
    """Ventas no anuladas que ocurrieron en el período y devoluciones hechas en el período."""
    sales = Sale.objects.filter(status=Sale.Status.COMPLETED, occurred_at__date__range=(start, end))
    returns = SaleReturn.objects.filter(created_at__date__range=(start, end), sale__status=Sale.Status.COMPLETED)
    if register:
        sales = sales.filter(shift__register_id=register)
        returns = returns.filter(shift__register_id=register)
    if salesperson:
        sales = sales.filter(salesperson_id=salesperson)
        returns = returns.filter(sale__salesperson_id=salesperson)
    return sales, returns


def _grouped(sales, returns, sales_key, returns_key, name):
    """Ventas y devoluciones agrupadas por la misma clave, en filas con el neto."""
    sold = {
        row["k"]: row
        for row in sales.annotate(k=sales_key).values("k").annotate(n=Count("id"), total=Sum("total"))
    }
    back = {row["k"]: row["total"] for row in returns.annotate(k=returns_key).values("k").annotate(total=Sum("total"))}
    rows = []
    for key in sorted(set(sold) | set(back), key=str):
        total = sold[key]["total"] if key in sold else ZERO
        returned = back.get(key, ZERO)
        rows.append({
            name: str(key),
            "sales_count": sold[key]["n"] if key in sold else 0,
            "total": money(total),
            "returns": money(returned),
            "net": money(total - returned),
        })
    return rows


def sales_report(start, end, register=None, salesperson=None):
    sales, returns = period_querysets(start, end, register, salesperson)

    s = sales.aggregate(n=Count("id"), total=Sum("total"), subtotal=Sum("subtotal"), tax=Sum("tax"))
    r = SaleReturnLine.objects.filter(sale_return__in=returns).aggregate(
        total=Sum("total"), subtotal=Sum("subtotal"), tax=Sum("tax"),
    )
    gross, subtotal, tax = s["total"] or ZERO, s["subtotal"] or ZERO, s["tax"] or ZERO
    r_total, r_subtotal, r_tax = r["total"] or ZERO, r["subtotal"] or ZERO, r["tax"] or ZERO

    paid = {p["method"]: p["total"] for p in Payment.objects.filter(sale__in=sales).values("method").annotate(total=Sum("amount"))}
    refunded = {
        p["method"]: p["total"]
        for p in Refund.objects.filter(sale_return__in=returns).values("method").annotate(total=Sum("amount"))
    }
    by_method = [
        {
            "method": method, "label": label,
            "payments": money(paid.get(method)), "refunds": money(refunded.get(method)),
            "net": money((paid.get(method) or ZERO) - (refunded.get(method) or ZERO)),
        }
        for method, label in Payment.Method.choices
        if paid.get(method) or refunded.get(method)
    ]

    return {
        "from": start.isoformat(),
        "to": end.isoformat(),
        "totals": {
            "sales_count": s["n"],
            "total": money(gross),
            "subtotal": money(subtotal),
            "tax": money(tax),
            "returns_total": money(r_total),
            "returns_subtotal": money(r_subtotal),
            "returns_tax": money(r_tax),
            "net_total": money(gross - r_total),
            "net_subtotal": money(subtotal - r_subtotal),
            "net_tax": money(tax - r_tax),
            "average_ticket": money(gross / s["n"] if s["n"] else ZERO),
        },
        "by_day": _grouped(sales, returns, TruncDate("occurred_at"), TruncDate("created_at"), "day"),
        "by_register": _grouped(sales, returns, F("shift__register__code"), F("shift__register__code"), "register"),
        "by_salesperson": _grouped(
            sales, returns, F("salesperson__username"), F("sale__salesperson__username"), "salesperson",
        ),
        "by_method": by_method,
    }


def products_report(start, end, register=None, limit=20):
    sales, returns = period_querysets(start, end, register)
    stats = {}
    sold = (
        SaleLine.objects.filter(sale__in=sales)
        .values("product")
        # La salida es negativa en el kardex; un servicio no tiene movimiento y se vende en su unidad base (spec 010).
        .annotate(q=Sum(Coalesce(-F("movement__quantity"), "quantity")), total=Sum("total"), subtotal=Sum("subtotal"),
                  n=Count("sale", distinct=True))
    )
    for row in sold:
        stats[row["product"]] = {"q": row["q"], "total": row["total"], "subtotal": row["subtotal"], "n": row["n"]}
    back = (
        SaleReturnLine.objects.filter(sale_return__in=returns)
        .values(product=F("sale_line__product"))
        .annotate(q=Sum(Coalesce("movement__quantity", "quantity")), total=Sum("total"), subtotal=Sum("subtotal"))
    )
    for row in back:  # también restan devoluciones de ventas de otro período
        st = stats.setdefault(row["product"], {"q": ZERO, "total": ZERO, "subtotal": ZERO, "n": 0})
        st["q"] -= row["q"]
        st["total"] -= row["total"]
        st["subtotal"] -= row["subtotal"]

    products = Product.objects.select_related("base_unit").in_bulk(stats.keys())
    items = [
        (st, {
            "product": pid, "sku": products[pid].sku, "name": products[pid].name, "unit": products[pid].base_unit.code,
            "sales_count": st["n"], "quantity": qty(st["q"]), "total": money(st["total"]), "subtotal": money(st["subtotal"]),
        })
        for pid, st in stats.items()
    ]
    by_quantity = [row for _, row in sorted(items, key=lambda i: (-i[0]["q"], i[1]["sku"]))[:limit]]
    by_value = [row for _, row in sorted(items, key=lambda i: (-i[0]["total"], i[1]["sku"]))[:limit]]

    # Sin movimiento = sin ventas válidas en el período (una venta anulada no cuenta como movimiento).
    moved = set(SaleLine.objects.filter(sale__in=sales).values_list("product_id", flat=True))
    stock = {r["product"]: r["q"] for r in StockLevel.objects.values("product").annotate(q=Sum("quantity"))}
    not_moved = [
        {"product": p.pk, "sku": p.sku, "name": p.name, "unit": p.base_unit.code, "stock": qty(stock.get(p.pk))}
        for p in Product.objects.filter(is_active=True, is_service=False).exclude(pk__in=moved).select_related("base_unit").order_by("sku")
    ]
    return {
        "from": start.isoformat(), "to": end.isoformat(),
        "by_quantity": by_quantity, "by_value": by_value, "not_moved": not_moved,
    }
