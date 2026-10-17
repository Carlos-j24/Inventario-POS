"""Spec 002, T3: cobrar un pedido en caja."""
import datetime
import threading
import uuid
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import connection

from apps.catalog.models import Unit
from apps.inventory.models import StockLevel, StockMovement
from apps.inventory.services import record_movement
from apps.sales.models import Order, Sale, business_date
from apps.sales.orders import cancel_order, create_order
from apps.sales.services import create_sale

pytestmark = pytest.mark.django_db
D = Decimal
CASH = [{"method": "CASH", "amount": D("10000000")}]


@pytest.fixture
def vendor(make_user):
    return make_user("andres", "Ventas")


@pytest.fixture
def cashier(make_user):
    return make_user("laura", "Caja")


@pytest.fixture
def stocked(cashier, warehouse, cable, hammer):
    for product, qty in ((cable, 300), (hammer, 10)):
        record_movement(kind=StockMovement.Kind.RECEIPT, product=product, warehouse=warehouse, quantity=qty, user=cashier)


@pytest.fixture
def order(vendor, cable, hammer, stocked):
    """12,5 m de cable (40.000) + 2 martillos (56.000) = 96.000."""
    order, _ = create_order(user=vendor, client_uuid=uuid.uuid4(), lines=[
        {"product": cable, "quantity": D("12.5")},
        {"product": hammer, "quantity": 2},
    ])
    return order


def line(order, product):
    return order.lines.get(product=product)


def charge(cashier, shift, order, lines=None, key=None, **extra):
    return create_sale(
        user=cashier, shift=shift, order=order, lines=lines, payments=CASH,
        client_uuid=key or uuid.uuid4(), **extra,
    )


def stock(product):
    return StockLevel.objects.get(product=product).quantity


def test_full_order_becomes_a_sale_by_vendor_charged_by_cashier(vendor, cashier, shift, order, cable, hammer):
    sale, created = charge(cashier, shift, order)
    assert created
    assert sale.total == D("96000.00")
    assert sale.salesperson == vendor
    assert sale.seller == cashier
    order.refresh_from_db()
    assert order.status == Order.Status.PAID
    assert order.sale == sale
    assert stock(cable) == D("287.5")
    assert stock(hammer) == 8
    assert not sale.needs_review


def test_cashier_can_charge_less_than_ordered(cashier, shift, order, cable, hammer):
    sale, _ = charge(cashier, shift, order, lines=[{"order_line": line(order, hammer), "quantity": 1}])
    assert sale.total == D("28000.00")
    assert [(l.product.sku, l.quantity) for l in sale.lines.all()] == [("MAR-16", D("1"))]
    assert stock(cable) == 300  # el cable no se lo llevó
    order.refresh_from_db()
    assert order.status == Order.Status.PAID


def test_cannot_charge_more_than_ordered(cashier, shift, order, hammer):
    with pytest.raises(ValidationError, match="más"):
        charge(cashier, shift, order, lines=[{"order_line": line(order, hammer), "quantity": 3}])
    with pytest.raises(ValidationError, match="más"):  # repartido en dos líneas tampoco
        charge(cashier, shift, order, lines=[
            {"order_line": line(order, hammer), "quantity": 2},
            {"order_line": line(order, hammer), "quantity": 1},
        ])
    assert not Sale.objects.exists()
    assert stock(hammer) == 10


def test_line_from_another_order_is_rejected(vendor, cashier, shift, order, hammer):
    other, _ = create_order(user=vendor, client_uuid=uuid.uuid4(), lines=[{"product": hammer, "quantity": 1}])
    with pytest.raises(ValidationError, match="no pertenece"):
        charge(cashier, shift, order, lines=[{"order_line": other.lines.get(), "quantity": 1}])


def test_empty_selection_is_rejected(cashier, shift, order):
    with pytest.raises(ValidationError):
        charge(cashier, shift, order, lines=[])


def test_order_is_charged_only_once(cashier, shift, order, hammer):
    first, _ = charge(cashier, shift, order)
    with pytest.raises(ValidationError, match="ya fue cobrado"):
        charge(cashier, shift, order)
    assert Sale.objects.count() == 1
    assert stock(hammer) == 8


def test_retry_with_same_client_uuid_returns_the_same_sale(cashier, shift, order):
    key = uuid.uuid4()
    first, _ = charge(cashier, shift, order, key=key)
    again, created = charge(cashier, shift, order, key=key)
    assert not created
    assert again.pk == first.pk


def test_cancelled_or_expired_orders_cannot_be_charged(vendor, cashier, shift, order, hammer):
    cancel_order(order=order, user=vendor)
    with pytest.raises(ValidationError, match="cancelado"):
        charge(cashier, shift, order)
    old, _ = create_order(user=vendor, client_uuid=uuid.uuid4(), lines=[{"product": hammer, "quantity": 1}])
    Order.objects.filter(pk=old.pk).update(business_date=business_date() - datetime.timedelta(days=1))
    with pytest.raises(ValidationError, match="vencido"):
        charge(cashier, shift, old)
    assert not Sale.objects.exists()


def test_order_price_wins_and_sale_goes_to_review(cashier, shift, order, hammer):
    hammer.sale_price = D("30000")  # el catálogo sube después del pedido
    hammer.save()
    sale, _ = charge(cashier, shift, order, lines=[{"order_line": line(order, hammer), "quantity": 2}])
    sale_line = sale.lines.get()
    assert sale_line.unit_price == D("28000.00")
    assert sale_line.catalog_price == D("30000.00")
    assert sale.total == D("56000.00")
    assert sale.needs_review


def test_presentation_lines_are_charged_in_their_unit(vendor, cashier, shift, cable, stocked):
    order, _ = create_order(user=vendor, client_uuid=uuid.uuid4(), lines=[
        {"product": cable, "quantity": 1, "unit": Unit.objects.get(code="rollo")},
    ])
    sale, _ = charge(cashier, shift, order)
    assert sale.total == D("320000.00")
    assert stock(cable) == 200


def test_orders_cannot_be_charged_offline(cashier, shift, order):
    with pytest.raises(ValidationError, match="conexión"):
        charge(cashier, shift, order, offline=True)


def test_payment_failure_leaves_order_pending(cashier, shift, order, hammer):
    with pytest.raises(ValidationError):
        create_sale(
            user=cashier, shift=shift, order=order, lines=None, client_uuid=uuid.uuid4(),
            payments=[{"method": "CASH", "amount": D("1000")}],
        )
    order.refresh_from_db()
    assert order.status == Order.Status.PENDING
    assert stock(hammer) == 10


def test_without_stock_the_order_is_not_charged(vendor, cashier, shift, hammer, stocked):
    big, _ = create_order(user=vendor, client_uuid=uuid.uuid4(), lines=[{"product": hammer, "quantity": 50}])
    with pytest.raises(ValidationError):
        charge(cashier, shift, big)
    big.refresh_from_db()
    assert big.status == Order.Status.PENDING


@pytest.mark.skipif(connection.vendor == "sqlite", reason="SQLite no permite escrituras concurrentes")
@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_two_cashiers_charging_at_once_produce_one_sale(cashier, shift, order):  # pragma: no cover
    errors = []

    def attempt():
        try:
            charge(cashier, shift, order)
        except ValidationError as exc:
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert Sale.objects.count() == 1
    assert len(errors) == 1
