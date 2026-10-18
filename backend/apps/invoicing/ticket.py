"""Representación gráfica del documento para el tiquete de 80 mm (spec 005, T6; Res. 165 de 2023, art. 19).

Se arma en el servidor con los mismos datos del documento electrónico. El QR solo existe cuando la
DIAN validó (lleva el CUDE); sin validar, el tiquete lo dice.
"""
from collections import defaultdict
from decimal import Decimal

import segno

from apps.cash.models import Payment

from .models import Business, FiscalDocument

Kind = FiscalDocument.Kind
TITLES = {
    Kind.POS: "Documento equivalente electrónico POS",
    Kind.INVOICE: "Factura electrónica de venta",
}
LEGEND = "Documento validado por la DIAN"


def money(value):
    return str(Decimal(value).quantize(Decimal("0.01")))


def qr_svg(data):
    """QR en SVG para imprimir (nivel de corrección M, sin margen extra)."""
    return segno.make(data, error="m").svg_inline(scale=3, border=2) if data else None


def business_data():
    b = Business.load()
    return {
        "name": b.name, "trade_name": b.trade_name, "nit": f"{b.nit}-{b.check_digit}" if b.nit else "",
        "address": b.address, "city": b.city, "phone": b.phone, "email": b.email, "tax_regime": b.tax_regime,
    }


def resolution_text(resolution):
    if resolution is None:
        return None
    return (
        f"Resolución DIAN {resolution.number} del {resolution.issued_on:%Y-%m-%d}: "
        f"{resolution.prefix}{resolution.range_from} a {resolution.prefix}{resolution.range_to}, "
        f"vigente hasta {resolution.valid_until:%Y-%m-%d}"
    )


def ticket_for_sale(sale):
    """Datos del tiquete de una venta, con su documento POS o factura si lo tiene."""
    document = sale.fiscal_documents.filter(kind__in=TITLES).select_related("customer", "resolution").first()
    lines = list(sale.lines.select_related("product", "unit"))
    taxes = defaultdict(lambda: {"base": Decimal(0), "tax": Decimal(0)})
    for line in lines:
        key = "excluido" if line.vat_excluded else f"{line.tax_rate.normalize():f}"
        taxes[key]["base"] += line.subtotal
        taxes[key]["tax"] += line.tax
    payments = list(sale.payments.all())
    labels = dict(Payment.Method.choices)
    notes = []
    if document is None:
        title, code, status = "Comprobante de venta", None, None
        notes.append("Sin documento electrónico: la facturación electrónica no está activa.")
    else:
        title, code, status = TITLES[document.kind], document.code, document.status
        if document.contingency:
            notes.append("Emitido en contingencia: se transmitió a la DIAN después de la venta.")
        if status == FiscalDocument.Status.VALIDATED:
            notes.append(LEGEND)
        elif status == FiscalDocument.Status.PENDING:
            notes.append("Pendiente de validación por la DIAN.")
        else:
            notes.append("Rechazado por la DIAN: el supervisor debe revisarlo.")
    customer = document.customer if document else None
    return {
        "business": business_data(),
        "title": title,
        "code": code,
        "status": status,
        "document_id": document.pk if document else None,
        "sale_number": sale.number,
        "issued_at": (document.issued_at if document else sale.occurred_at).isoformat(),
        "register": sale.shift.register.code,
        "cashier": sale.seller.username,
        "customer": None if customer is None or customer.is_final_consumer else {
            "name": customer.name,
            "document": f"{customer.get_id_type_display()} {customer.id_number}"
            + (f"-{customer.check_digit}" if customer.check_digit else ""),
        },
        "lines": [
            {
                "name": line.product.name, "quantity": str(line.quantity), "unit": line.unit.code,
                "unit_price": money(line.unit_price), "total": money(line.total),
            }
            for line in lines
        ],
        "subtotal": money(sale.subtotal),
        "tax": money(sale.tax),
        "total": money(sale.total),
        "taxes": [
            {"rate": rate, "base": money(v["base"]), "tax": money(v["tax"])} for rate, v in sorted(taxes.items())
        ],
        "payments": [{"label": labels[p.method], "amount": money(p.received)} for p in payments],
        "change": money(sum((p.change for p in payments), Decimal(0))),
        "cude": document.cude if document and document.cude else None,
        "qr_svg": qr_svg(document.qr_data) if document else None,  # solo hay QR tras validar
        "resolution": resolution_text(document.resolution) if document else None,
        "notes": notes,
    }
