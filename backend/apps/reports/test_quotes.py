"""Reporte de cotizaciones (spec 007, T6)."""
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.customers.models import Customer
from apps.inventory.models import StockMovement
from apps.inventory.services import record_movement
from apps.sales import quotes as service
from apps.sales.models import Quote, business_date
from apps.sales.orders import create_order
from apps.sales.services import create_sale

from . import quotes as report_module

pytestmark = pytest.mark.django_db
URL = "/api/reports/quotes/"
CASH = [{"method": "CASH", "amount": Decimal("10000000")}]


def api(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.fixture
def people(make_user):
    return {name: make_user(name, role) for name, role in (
        ("andres", "Ventas"), ("camilo", "Ventas"), ("laura", "Caja"), ("sofia", "Supervisor"),
    )}


@pytest.fixture
def scenario(people, warehouse, shift, hammer, cable):
    """andres: una convertida del todo, una a medias (y un pedido sin cobrar), una anulada y una vencida.
    camilo: una vigente sin nada. Y una de andres de la semana pasada, fuera del período."""
    andres, camilo, laura = people["andres"], people["camilo"], people["laura"]
    for product, qty in ((hammer, 100), (cable, 1000)):
        record_movement(kind=StockMovement.Kind.RECEIPT, product=product, warehouse=warehouse, quantity=qty, user=laura)

    def quote(user, *lines, name="Cliente", customer=None):
        q, _ = service.create_quote(user=user, client_uuid=uuid.uuid4(), customer_name=name, customer=customer,
                                    lines=[{"product": p, "quantity": Decimal(n)} for p, n in lines])
        return q

    def sell(q, *parts):
        order, _ = service.convert_quote(quote=q, user=andres, client_uuid=uuid.uuid4(),
                                         lines=[{"quote_line": q.lines.get(product=p), "quantity": Decimal(n)} for p, n in parts])
        create_sale(user=laura, shift=shift, order=order, lines=None, client_uuid=uuid.uuid4(), payments=CASH)

    full = quote(andres, (hammer, 2), name="Don Jorge")  # 56.000, todo cobrado
    sell(full, (hammer, 2))
    half = quote(andres, (hammer, 4), (cable, 10))  # 112.000 + 32.000 = 144.000
    sell(half, (hammer, 1))  # 28.000 cobrado
    service.convert_quote(quote=half, user=andres, client_uuid=uuid.uuid4(),
                          lines=[{"quote_line": half.lines.get(product=cable), "quantity": Decimal(10)}])  # pedido sin cobrar: no cuenta
    voided = quote(andres, (hammer, 1))  # 28.000
    service.void_quote(quote=voided, user=andres, note="No")
    expired = quote(andres, (hammer, 1))  # 28.000
    Quote.objects.filter(pk=expired.pk).update(valid_until=business_date() - timedelta(days=1))
    builder = Customer.objects.create(id_number="900123456", name="Constructora Los Pinos")
    quote(camilo, (cable, 100), name="", customer=builder)  # 320.000, a un cliente registrado
    old = quote(andres, (hammer, 10))
    Quote.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=7))
    return {"full": full, "half": half}


def test_totals_by_status_and_conversion_rate(people, scenario):
    data = api(people["sofia"]).get(URL).data  # por defecto, hoy
    assert data["totals"] == {
        "quotes": 5, "quoted": "576000.00", "converted": "84000.00", "rate": "14.6", "with_sales": 2,
        "by_status": {"VALID": 2, "CONVERTED": 1, "VOIDED": 1, "EXPIRED": 1},
    }
    assert data["by_salesperson"] == [
        {"salesperson": "camilo", "quotes": 1, "with_sales": 0, "quoted": "320000.00", "converted": "0.00", "rate": "0.0"},
        {"salesperson": "andres", "quotes": 4, "with_sales": 2, "quoted": "256000.00", "converted": "84000.00", "rate": "32.8"},
    ]  # el que más cotizó primero


def test_detail_rows_newest_first(people, scenario):
    rows = api(people["sofia"]).get(URL).data["rows"]
    assert [r["created_by"] for r in rows] == ["camilo", "andres", "andres", "andres", "andres"]
    assert rows[0]["customer"] == "Constructora Los Pinos"  # sin nombre escrito: el del cliente registrado
    full = next(r for r in rows if r["number"] == scenario["full"].number)
    assert (full["customer"], full["status"], full["status_label"], full["total"], full["converted"]) == (
        "Don Jorge", "CONVERTED", "Convertida", "56000.00", "56000.00",
    )
    half = next(r for r in rows if r["number"] == scenario["half"].number)
    assert (half["status"], half["total"], half["converted"]) == ("VALID", "144000.00", "28000.00")


def test_period_and_salesperson_filters(people, scenario):
    week = {"from": str(business_date() - timedelta(days=7)), "to": str(business_date())}
    assert api(people["sofia"]).get(URL, week).data["totals"]["quotes"] == 6  # con la de la semana pasada
    mine = api(people["sofia"]).get(URL, {"salesperson": people["camilo"].pk}).data
    assert (mine["totals"]["quotes"], mine["totals"]["quoted"], [p["salesperson"] for p in mine["by_salesperson"]]) == (
        1, "320000.00", ["camilo"],
    )
    yesterday = str(business_date() - timedelta(days=1))
    empty = api(people["sofia"]).get(URL, {"from": yesterday, "to": yesterday}).data
    assert (empty["totals"]["quotes"], empty["totals"]["rate"], empty["rows"], empty["by_salesperson"]) == (0, "0.0", [], [])


def test_the_detail_is_capped(people, scenario, monkeypatch):
    monkeypatch.setattr(report_module, "DETAIL_LIMIT", 2)
    data = api(people["sofia"]).get(URL).data
    assert (len(data["rows"]), data["truncated"], data["totals"]["quotes"]) == (2, True, 5)  # los totales siguen completos
    monkeypatch.setattr(report_module, "DETAIL_LIMIT", 5)
    assert api(people["sofia"]).get(URL).data["truncated"] is False


def test_permissions(people, make_user):
    assert api(people["andres"]).get(URL).status_code == 403  # Ventas no ve reportes
    assert api(make_user("marta", "Jefe de bodega")).get(URL).status_code == 200  # reports.view
    assert APIClient().get(URL).status_code == 403
