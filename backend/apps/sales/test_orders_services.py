"""Spec 002, T2: crear, cancelar y vencer pedidos."""
import datetime
import uuid
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command

from apps.catalog.models import Unit
from apps.inventory.models import StockLevel, StockMovement
from apps.inventory.services import record_movement
from apps.sales import orders
from apps.sales.models import Order, business_date
from apps.sales.orders import cancel_order, create_order, expire_orders, stock_warnings

pytestmark = pytest.mark.django_db
D = Decimal


@pytest.fixture
def vendor(make_user):
    return make_user("andres", "Ventas")


def order_of(vendor, lines, key=None):
    return create_order(user=vendor, lines=lines, client_uuid=key or uuid.uuid4())


# --- crear ------------------------------------------------------------------

def test_create_freezes_catalog_prices_and_total(vendor, cable, hammer):
    order, created = order_of(vendor, [
        {"product": cable, "quantity": D("12.5")},
        {"product": cable, "quantity": 1, "unit": Unit.objects.get(code="rollo")},
        {"product": hammer, "quantity": 2},
    ])
    assert created
    assert order.status == Order.Status.PENDING
    assert order.salesperson == vendor
    assert 1000 <= order.code <= 9999
    prices = sorted((str(l.quantity), str(l.unit_price), str(l.total)) for l in order.lines.all())
    assert prices == sorted([
        ("12.500", "3200.00", "40000.00"),
        ("1.000", "320000.00", "320000.00"),   # rollo = 100 m × 3.200
        ("2.000", "28000.00", "56000.00"),
    ])
    assert order.total == D("416000.00")


def test_order_does_not_move_stock(vendor, warehouse, hammer):
    record_movement(kind=StockMovement.Kind.RECEIPT, product=hammer, warehouse=warehouse, quantity=5, user=vendor)
    order_of(vendor, [{"product": hammer, "quantity": 3}])
    assert StockLevel.objects.get(product=hammer).quantity == 5
    assert StockMovement.objects.count() == 1


def test_order_without_lines_is_rejected(vendor):
    with pytest.raises(ValidationError):
        order_of(vendor, [])


@pytest.mark.parametrize("quantity, unit_code", [
    (0, None),
    (D("0.5"), None),   # el martillo no se vende fraccionado
    (1, "rollo"),       # unidad que el martillo no maneja
])
def test_invalid_lines_are_rejected(vendor, hammer, quantity, unit_code):
    line = {"product": hammer, "quantity": quantity}
    if unit_code:
        line["unit"] = Unit.objects.get(code=unit_code)
    with pytest.raises(ValidationError):
        order_of(vendor, [line])
    assert not Order.objects.exists()


def test_same_client_uuid_creates_one_order(vendor, hammer):
    key = uuid.uuid4()
    first, _ = order_of(vendor, [{"product": hammer, "quantity": 1}], key)
    again, created = order_of(vendor, [{"product": hammer, "quantity": 1}], key)
    assert not created
    assert again.pk == first.pk
    assert Order.objects.count() == 1


def test_code_collision_retries_with_another_code(vendor, hammer, monkeypatch):
    taken, _ = order_of(vendor, [{"product": hammer, "quantity": 1}])
    codes = iter([taken.code, taken.code, 5555])
    monkeypatch.setattr(orders, "_random_code", lambda: next(codes))
    order, _ = order_of(vendor, [{"product": hammer, "quantity": 1}])
    assert order.code == 5555
    assert order.lines.count() == 1  # las líneas del intento fallido no quedan sueltas


def test_codes_exhausted_gives_clear_error(vendor, hammer, monkeypatch):
    taken, _ = order_of(vendor, [{"product": hammer, "quantity": 1}])
    monkeypatch.setattr(orders, "_random_code", lambda: taken.code)
    with pytest.raises(ValidationError, match="códigos"):
        order_of(vendor, [{"product": hammer, "quantity": 1}])


def test_yesterdays_code_can_be_reused_today(vendor, hammer, monkeypatch):
    old, _ = order_of(vendor, [{"product": hammer, "quantity": 1}])
    Order.objects.filter(pk=old.pk).update(business_date=business_date() - datetime.timedelta(days=1))
    monkeypatch.setattr(orders, "_random_code", lambda: old.code)
    order, _ = order_of(vendor, [{"product": hammer, "quantity": 1}])
    assert order.code == old.code


# --- cancelar ---------------------------------------------------------------

def test_vendor_cancels_own_order(vendor, hammer):
    order, _ = order_of(vendor, [{"product": hammer, "quantity": 1}])
    cancel_order(order=order, user=vendor)
    order.refresh_from_db()
    assert order.status == Order.Status.CANCELLED
    assert order.cancelled_by == vendor


def test_other_vendor_cannot_cancel_but_supervisor_can(make_user, vendor, hammer):
    order, _ = order_of(vendor, [{"product": hammer, "quantity": 1}])
    with pytest.raises(PermissionDenied):
        cancel_order(order=order, user=make_user("otra", "Ventas"))
    cancel_order(order=order, user=make_user("sofia", "Supervisor"))
    order.refresh_from_db()
    assert order.status == Order.Status.CANCELLED


def test_cannot_cancel_twice_or_expired(vendor, hammer):
    order, _ = order_of(vendor, [{"product": hammer, "quantity": 1}])
    cancel_order(order=order, user=vendor)
    with pytest.raises(ValidationError):
        cancel_order(order=order, user=vendor)
    old, _ = order_of(vendor, [{"product": hammer, "quantity": 1}])
    Order.objects.filter(pk=old.pk).update(business_date=business_date() - datetime.timedelta(days=1))
    with pytest.raises(ValidationError, match="vencido"):
        cancel_order(order=old, user=vendor)


# --- vencer -----------------------------------------------------------------

def test_expire_marks_only_pending_orders_from_previous_days(vendor, hammer):
    today_order, _ = order_of(vendor, [{"product": hammer, "quantity": 1}])
    old, _ = order_of(vendor, [{"product": hammer, "quantity": 1}])
    old_cancelled, _ = order_of(vendor, [{"product": hammer, "quantity": 1}])
    cancel_order(order=old_cancelled, user=vendor)
    yesterday = business_date() - datetime.timedelta(days=1)
    Order.objects.filter(pk__in=[old.pk, old_cancelled.pk]).update(business_date=yesterday)

    assert expire_orders() == 1
    statuses = dict(Order.objects.values_list("pk", "status"))
    assert statuses[today_order.pk] == "PENDING"
    assert statuses[old.pk] == "EXPIRED"
    assert statuses[old_cancelled.pk] == "CANCELLED"


def test_expire_command(vendor, hammer, capsys):
    old, _ = order_of(vendor, [{"product": hammer, "quantity": 1}])
    Order.objects.filter(pk=old.pk).update(business_date=business_date() - datetime.timedelta(days=2))
    call_command("expire_orders")
    assert "Pedidos vencidos: 1" in capsys.readouterr().out


# --- avisos de stock ----------------------------------------------------------

def test_stock_warnings_only_warn(vendor, warehouse, cable, hammer):
    record_movement(kind=StockMovement.Kind.RECEIPT, product=cable, warehouse=warehouse, quantity=120, user=vendor)
    record_movement(kind=StockMovement.Kind.RECEIPT, product=hammer, warehouse=warehouse, quantity=1, user=vendor)
    order, _ = order_of(vendor, [
        {"product": cable, "quantity": 1, "unit": Unit.objects.get(code="rollo")},  # quedan 20 m < mínimo 50
        {"product": hammer, "quantity": 3},                                         # hay 1
    ])
    warnings = {w["sku"]: (w["kind"], w["available"]) for w in stock_warnings(order)}
    assert warnings == {"CAB-12": ("bajo_minimo", D("120")), "MAR-16": ("sin_existencias", D("1"))}
    assert order.status == Order.Status.PENDING  # el pedido se creó igual


def test_no_warnings_when_stock_is_fine(vendor, warehouse, hammer):
    record_movement(kind=StockMovement.Kind.RECEIPT, product=hammer, warehouse=warehouse, quantity=50, user=vendor)
    order, _ = order_of(vendor, [{"product": hammer, "quantity": 2}])
    assert stock_warnings(order) == []
