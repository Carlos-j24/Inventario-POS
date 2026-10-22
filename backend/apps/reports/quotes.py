"""Reporte de cotizaciones (spec 007, T6): cuánto se cotizó y cuánto se convirtió en venta.

Toma las cotizaciones creadas en el período (fecha de Bogotá). De cada una, "convertido" es lo ya cobrado
de sus pedidos al precio cotizado, aunque se haya cobrado después del período: la pregunta es qué pasó con
lo que se cotizó entonces. Lo que está en un pedido sin cobrar todavía no cuenta.
"""
from decimal import Decimal

from django.db.models import Prefetch

from apps.sales.models import Quote, QuoteLine
from apps.sales.quotes import charged

from .services import ZERO, money

DETAIL_LIMIT = 500
STATUSES = list(Quote.Status.values)


def _rate(converted, quoted):
    """Porcentaje convertido del valor cotizado, con un decimal."""
    return str((converted * 100 / quoted).quantize(Decimal("0.1"))) if quoted else "0.0"


def quotes_report(start, end, salesperson=None):
    quotes = (
        Quote.objects.filter(created_at__date__range=(start, end))
        .select_related("created_by", "customer")
        .prefetch_related(Prefetch("lines", queryset=QuoteLine.objects.select_related("product", "unit")))
        .order_by("-created_at", "-pk")
    )
    if salesperson:
        quotes = quotes.filter(created_by_id=salesperson)

    totals = {"quoted": ZERO, "converted": ZERO}
    counts = dict.fromkeys(STATUSES, 0)
    with_sales = 0
    people = {}
    rows = []
    for quote in quotes:
        status = quote.effective_status()
        converted = sum((charged(line) * line.unit_price for line in quote.lines.all()), ZERO)
        converted = converted.quantize(Decimal("0.01"))
        totals["quoted"] += quote.total
        totals["converted"] += converted
        counts[status] += 1
        with_sales += converted > 0
        person = people.setdefault(quote.created_by.username, {"quotes": 0, "quoted": ZERO, "converted": ZERO, "with_sales": 0})
        person["quotes"] += 1
        person["quoted"] += quote.total
        person["converted"] += converted
        person["with_sales"] += converted > 0
        if len(rows) < DETAIL_LIMIT:
            rows.append({
                "id": quote.pk, "number": quote.number, "created_at": quote.created_at.isoformat(),
                "customer": quote.customer_label, "created_by": quote.created_by.username,
                "status": status, "status_label": Quote.Status(status).label,
                "total": money(quote.total), "converted": money(converted),
            })
    count = sum(counts.values())
    return {
        "from": start.isoformat(), "to": end.isoformat(),
        "totals": {
            "quotes": count,
            "quoted": money(totals["quoted"]),
            "converted": money(totals["converted"]),
            "rate": _rate(totals["converted"], totals["quoted"]),
            "with_sales": with_sales,
            "by_status": counts,
        },
        "by_salesperson": [
            {"salesperson": name, "quotes": p["quotes"], "with_sales": p["with_sales"], "quoted": money(p["quoted"]),
             "converted": money(p["converted"]), "rate": _rate(p["converted"], p["quoted"])}
            for name, p in sorted(people.items(), key=lambda item: (-item[1]["quoted"], item[0]))
        ],
        "rows": rows,
        "truncated": count > DETAIL_LIMIT,
    }
