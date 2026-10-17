"""Reportes con costos (spec 004, T3): inventario valorizado y márgenes. Permiso reports.costs.

- Inventario valorizado: foto actual. Cada existencia vale cantidad × costo promedio; una existencia
  en negativo (ventas sin conexión) vale 0, porque no se puede tener mercancía negativa, y se marca.
- Márgenes: venta neta sin IVA − costo de lo vendido, con las mismas reglas de período que el
  reporte de ventas. El costo es el que quedó guardado en el movimiento al vender (no cambia
  después); las devoluciones restan con el costo con que volvieron.
"""
from decimal import Decimal

from django.db.models import F, Q

from apps.catalog.models import Product
from apps.inventory.models import StockLevel
from apps.sales.models import SaleLine, SaleReturnLine

from .services import ZERO, money, period_querysets, qty

COST_PLACES = Decimal("0.0001")


def percent(part, whole):
    """Porcentaje con un decimal, o None si no hay base (no se puede dividir entre 0)."""
    return str((part * 100 / whole).quantize(Decimal("0.1"))) if whole else None


def inventory_report(warehouse=None):
    levels = StockLevel.objects.all()
    if warehouse:
        levels = levels.filter(warehouse_id=warehouse)
    stats = {}
    for level in levels.values("product", "quantity", "average_cost"):
        st = stats.setdefault(level["product"], {"q": ZERO, "positive": ZERO, "value": ZERO, "negative": False})
        st["q"] += level["quantity"]
        if level["quantity"] < 0:
            st["negative"] = True
        else:
            st["positive"] += level["quantity"]
            st["value"] += level["quantity"] * level["average_cost"]

    # Productos activos, y los inactivos que todavía tienen existencias.
    held = [pid for pid, st in stats.items() if st["q"]]
    products = Product.objects.filter(Q(is_active=True) | Q(pk__in=held)).select_related("base_unit").order_by("sku")
    rows = []
    for p in products:
        st = stats.get(p.pk, {"q": ZERO, "positive": ZERO, "value": ZERO, "negative": False})
        rows.append({
            "product": p.pk, "sku": p.sku, "name": p.name, "unit": p.base_unit.code,
            "stock": qty(st["q"]), "min_stock": qty(p.min_stock),
            "average_cost": str((st["value"] / st["positive"]).quantize(COST_PLACES)) if st["positive"] else None,
            "value": money(st["value"]),
            "below_min": p.min_stock > 0 and st["q"] < p.min_stock,
            "negative": st["negative"],
        })
    return {
        "totals": {
            "value": money(sum((stats[r["product"]]["value"] for r in rows if r["product"] in stats), ZERO)),
            "products": len(rows),
            "below_min": sum(r["below_min"] for r in rows),
            "negative": sum(r["negative"] for r in rows),
        },
        "rows": rows,
    }


def margins_report(start, end, register=None):
    sales, returns = period_querysets(start, end, register)
    stats = {}

    def add(product, net, quantity, unit_cost, estimated):
        st = stats.setdefault(product, {"net": ZERO, "cost": ZERO, "estimated": False})
        st["net"] += net
        st["cost"] += quantity * (unit_cost or ZERO)
        st["estimated"] |= bool(estimated) or unit_cost is None

    fields = ("subtotal", "movement__quantity", "movement__unit_cost", "movement__cost_estimated")
    for line in SaleLine.objects.filter(sale__in=sales).values("product", *fields):
        # La salida es negativa en el kardex: -cantidad es lo vendido.
        add(line["product"], line["subtotal"], -line["movement__quantity"],
            line["movement__unit_cost"], line["movement__cost_estimated"])
    for line in SaleReturnLine.objects.filter(sale_return__in=returns).values(*fields, product=F("sale_line__product")):
        add(line["product"], -line["subtotal"], -line["movement__quantity"],
            line["movement__unit_cost"], line["movement__cost_estimated"])

    products = Product.objects.select_related("base_unit").in_bulk(stats.keys())
    rows = []
    for pid, st in stats.items():
        margin = st["net"] - st["cost"]
        rows.append({
            "product": pid, "sku": products[pid].sku, "name": products[pid].name,
            "net_sales": money(st["net"]), "cost": money(st["cost"]), "margin": money(margin),
            "margin_pct": percent(margin, st["net"]), "cost_estimated": st["estimated"],
            "_margin": margin,
        })
    rows.sort(key=lambda r: (-r["_margin"], r["sku"]))
    for row in rows:
        del row["_margin"]

    net = sum((st["net"] for st in stats.values()), ZERO)
    cost = sum((st["cost"] for st in stats.values()), ZERO)
    return {
        "from": start.isoformat(), "to": end.isoformat(),
        "totals": {
            "net_sales": money(net), "cost": money(cost), "margin": money(net - cost),
            "margin_pct": percent(net - cost, net),
            "cost_estimated": any(st["estimated"] for st in stats.values()),
        },
        "rows": rows,
    }
