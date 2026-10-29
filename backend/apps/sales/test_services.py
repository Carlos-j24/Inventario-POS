"""Servicios en la caja (spec 010, T2): un lavado se cobra, anula y devuelve sin tocar el inventario."""
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework.test import APIClient

from apps.cash.services import shift_summary
from apps.catalog.models import Category, Product, Unit
from apps.inventory.models import StockLevel, StockMovement
from apps.inventory.services import record_movement

from . import quotes
from .orders import create_order, stock_warnings
from .returns import create_return, void_sale
from .services import create_sale

pytestmark = pytest.mark.django_db
D = Decimal


def api(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.fixture
def cashier(make_user):
    return make_user("laura", "Caja")


@pytest.fixture
def wash(db):
    return Product.objects.create(
        sku="LAV-150", name="Lavado moto hasta 150 cc", category=Category.objects.create(name="Lavadero"),
        base_unit=Unit.objects.get(code="und"), sale_price=D("12000"), is_service=True,
    )


@pytest.fixture
def oil(cashier, warehouse):
    product = Product.objects.create(
        sku="ACE-20W50", name="Aceite 20W50", category=Category.objects.create(name="Lubricantes"),
        base_unit=Unit.objects.get(code="und"), sale_price=D("30000"),
    )
    record_movement(kind=StockMovement.Kind.RECEIPT, product=product, warehouse=warehouse, quantity=5, user=cashier, unit_cost="20000")
    return product


def stock(product, warehouse):
    return StockLevel.objects.get(product=product, warehouse=warehouse).quantity


def charge(cashier, shift, *lines, offline=False, paid=None, **extra):
    total = sum(product.sale_price * qty for product, qty in lines)
    sale, _ = create_sale(user=cashier, shift=shift, client_uuid=uuid.uuid4(), offline=offline,
                          lines=[{"product": p, "quantity": q} for p, q in lines],
                          payments=[{"method": "CASH", "amount": paid or total}], **extra)
    return sale


# --- vender -------------------------------------------------------------------

def test_a_wash_is_charged_online_without_stock_and_without_review(cashier, shift, wash, warehouse):
    sale = charge(cashier, shift, (wash, 2))
    line = sale.lines.get()
    assert (line.is_service, line.movement, line.total, sale.total) == (True, None, D("24000.00"), D("24000.00"))
    assert sale.needs_review is False
    assert not StockMovement.objects.filter(product=wash).exists()
    assert not StockLevel.objects.filter(product=wash).exists()


def test_wash_and_oil_together_only_the_oil_leaves_the_warehouse(cashier, shift, wash, oil, warehouse):
    sale = charge(cashier, shift, (wash, 1), (oil, 1))
    assert stock(oil, warehouse) == 4
    oil_line = sale.lines.get(product=oil)
    assert (oil_line.is_service, oil_line.movement.reference) == (False, f"Venta {sale.number}")
    assert StockMovement.objects.filter(sale_lines__sale=sale).count() == 1


def test_offline_wash_does_not_go_to_review(cashier, shift, wash):
    sale = charge(cashier, shift, (wash, 1), offline=True, occurred_at=timezone.now() - timedelta(minutes=20))
    assert (sale.offline, sale.needs_review) == (True, False)


def test_offline_wash_at_another_price_still_goes_to_review(cashier, shift, wash):
    sale, _ = create_sale(user=cashier, shift=shift, client_uuid=uuid.uuid4(), offline=True,
                          lines=[{"product": wash, "quantity": 1, "unit_price": D("10000")}],
                          payments=[{"method": "CASH", "amount": D("10000")}])
    assert (sale.total, sale.needs_review) == (D("10000.00"), True)  # decisión 2: precio fijo


def test_an_inactive_service_is_not_sold_online(cashier, shift, wash):
    Product.objects.filter(pk=wash.pk).update(is_active=False)
    wash.refresh_from_db()
    with pytest.raises(ValidationError, match="desactivado"):
        charge(cashier, shift, (wash, 1))


def test_the_till_api_charges_a_wash_and_shows_it_as_a_service(cashier, shift, wash):
    client = api(cashier)
    res = client.post("/api/sales/", {
        "client_uuid": str(uuid.uuid4()), "shift": shift.pk,
        "lines": [{"product": wash.pk, "quantity": "1"}], "payments": [{"method": "CASH", "amount": "12000"}],
    }, format="json")
    assert res.status_code == 201, res.data
    line = client.get(f"/api/sales/{res.data['id']}/").data["lines"][0]
    assert (line["product"], line["is_service"], line["total"]) == ("LAV-150", True, "12000.00")


# --- anular y devolver ----------------------------------------------------------

def test_voiding_returns_only_the_oil_and_all_the_money(make_user, cashier, shift, wash, oil, warehouse):
    sale = charge(cashier, shift, (wash, 1), (oil, 1))
    void_sale(sale=sale, user=make_user("sofia", "Supervisor"), reason="Error de digitación")
    assert stock(oil, warehouse) == 5
    assert StockMovement.objects.filter(kind="RETURN", reference=f"Anulación {sale.number}").count() == 1
    assert shift_summary(shift)["expected_cash"] == D("100000")


def test_voiding_a_sale_of_only_washes_moves_nothing(make_user, cashier, shift, wash):
    sale = charge(cashier, shift, (wash, 3))
    void_sale(sale=sale, user=make_user("sofia", "Supervisor"), reason="Cobrado dos veces")
    assert not StockMovement.objects.exists() and shift_summary(shift)["expected_cash"] == D("100000")


def test_returning_a_wash_refunds_without_movement(cashier, shift, wash, oil, warehouse):
    sale = charge(cashier, shift, (wash, 2), (oil, 1))
    wash_line, oil_line = sale.lines.get(product=wash), sale.lines.get(product=oil)
    back, _ = create_return(sale=sale, user=cashier, shift=shift, refund_method="CASH", reason="No se lavó",
                            client_uuid=uuid.uuid4(), lines=[{"sale_line": wash_line, "quantity": 1}, {"sale_line": oil_line, "quantity": 1}])
    wash_back, oil_back = back.lines.get(sale_line=wash_line), back.lines.get(sale_line=oil_line)
    assert (wash_back.movement, wash_back.total) == (None, D("12000.00"))
    assert oil_back.movement.reference == f"Devolución {back.number} de {sale.number}"
    assert stock(oil, warehouse) == 5
    assert back.total == D("42000.00")
    # Lo que queda del lavado se puede devolver después, y no más.
    create_return(sale=sale, user=cashier, shift=shift, refund_method="CASH", reason="El otro tampoco",
                  client_uuid=uuid.uuid4(), lines=[{"sale_line": wash_line, "quantity": 1}])
    with pytest.raises(ValidationError, match="se vendieron"):
        create_return(sale=sale, user=cashier, shift=shift, refund_method="CASH", reason="Otra vez",
                      client_uuid=uuid.uuid4(), lines=[{"sale_line": wash_line, "quantity": 1}])
    assert not StockMovement.objects.filter(product=wash).exists()


def test_review_reasons_skip_services(make_user, cashier, shift, wash):
    sale, _ = create_sale(user=cashier, shift=shift, client_uuid=uuid.uuid4(), offline=True,
                          lines=[{"product": wash, "quantity": 1, "unit_price": D("10000")}],
                          payments=[{"method": "CASH", "amount": D("10000")}])
    res = api(make_user("sofia", "Supervisor")).get("/api/sales/review/")
    assert res.status_code == 200
    assert [(s["id"], s["reasons"]) for s in res.data] == [(sale.pk, ["Precio distinto al del catálogo"])]


# --- pedidos y cotizaciones -----------------------------------------------------

def test_an_order_with_a_wash_warns_only_about_the_parts(make_user, wash, oil):
    vendor = make_user("andres", "Ventas")
    order, _ = create_order(user=vendor, client_uuid=uuid.uuid4(), lines=[{"product": wash, "quantity": 1}, {"product": oil, "quantity": 9}])
    assert [(w["sku"], w["kind"]) for w in stock_warnings(order)] == [("ACE-20W50", "sin_existencias")]


def test_an_order_of_a_wash_alone_has_no_warnings(make_user, wash):
    order, _ = create_order(user=make_user("andres", "Ventas"), client_uuid=uuid.uuid4(), lines=[{"product": wash, "quantity": 2}])
    assert stock_warnings(order) == []


def test_a_quoted_wash_becomes_an_order_and_is_charged(make_user, cashier, shift, wash, oil, warehouse):
    vendor = make_user("andres", "Ventas")
    quote, _ = quotes.create_quote(user=vendor, client_uuid=uuid.uuid4(), customer_name="Don Jorge",
                                   lines=[{"product": wash, "quantity": 1}, {"product": oil, "quantity": 1}])
    order, _ = quotes.convert_quote(quote=quote, user=vendor, client_uuid=uuid.uuid4(), lines=None)
    sale, _ = create_sale(user=cashier, shift=shift, order=order, client_uuid=uuid.uuid4(), lines=None,
                          payments=[{"method": "CASH", "amount": D("42000")}])
    assert sorted((l.product.sku, l.is_service, l.movement is None) for l in sale.lines.all()) == [
        ("ACE-20W50", False, False), ("LAV-150", True, True),
    ]
    assert (sale.needs_review, stock(oil, warehouse)) == (False, 4)
