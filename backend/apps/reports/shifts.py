"""Reporte de arqueos (spec 004, T3): turnos cerrados en el período, por la fecha de cierre."""
from apps.cash.models import Payment, Shift
from apps.cash.services import shift_summary

from .services import ZERO, money


def shifts_report(start, end, register=None):
    shifts = (
        Shift.objects.filter(status=Shift.Status.CLOSED, closed_at__date__range=(start, end))
        .select_related("register", "opened_by", "closed_by")
        .order_by("closed_at", "pk")
    )
    if register:
        shifts = shifts.filter(register_id=register)

    methods = Payment.Method.values
    totals = {"expected": ZERO, "counted": ZERO, "difference": ZERO, "shortage": ZERO, "overage": ZERO}
    by_method = {m: ZERO for m in methods}
    rows = []
    for shift in shifts:
        summary = shift_summary(shift)
        # Lo que entró por cada medio en el turno: cobros menos reembolsos (esperado − base, en efectivo).
        net = {m: summary["by_method"][m] - summary["refunds"][m] for m in methods}
        diff = shift.difference
        rows.append({
            "shift": shift.pk, "register": shift.register.code,
            "opened_by": shift.opened_by.username, "opened_at": shift.opened_at.isoformat(),
            "closed_by": shift.closed_by.username if shift.closed_by else None,
            "closed_at": shift.closed_at.isoformat(),
            "sales_count": summary["sales"],
            "opening_float": money(shift.opening_float),
            "by_method": {m: money(v) for m, v in net.items()},
            "expected_cash": money(shift.expected_cash),
            "counted_cash": money(shift.counted_cash),
            "difference": money(diff),
            "notes": shift.notes,
        })
        totals["expected"] += shift.expected_cash
        totals["counted"] += shift.counted_cash
        totals["difference"] += diff
        if diff < 0:
            totals["shortage"] -= diff
        else:
            totals["overage"] += diff
        for m in methods:
            by_method[m] += net[m]
    return {
        "from": start.isoformat(), "to": end.isoformat(),
        "totals": {
            "shifts": len(rows),
            "expected_cash": money(totals["expected"]),
            "counted_cash": money(totals["counted"]),
            "difference": money(totals["difference"]),
            "shortage": money(totals["shortage"]),
            "overage": money(totals["overage"]),
            "by_method": {m: money(v) for m, v in by_method.items()},
        },
        "rows": rows,
    }
