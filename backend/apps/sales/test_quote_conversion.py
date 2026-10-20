"""Convertir una cotización en pedido, por partes, y cobrarla (spec 007, T2)."""
import threading
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import connection

from apps.catalog.models import Unit
from apps.inventory.models import StockLevel, StockMovement
from apps.inventory.services import record_movement

from . import quotes as service
from .models import Order, Quote, business_date
from .orders import cancel_order, create_order
from .services import create_sale

pytestmark = pytest.mark.django_db
CASH = [{"method": "CASH", "amount": Decimal("10000000")}]


@pytest.fixture
def vendor(make_user):
    return make_user("andres", "Ventas")


@pytest.fixture
def cashier(make_user):
    return make_user("laura", "Caja")


@pytest.fixture
def stocked(vendor, warehouse, hammer, cable):
    for product, qty in ((hammer, 50), (cable, 1000)):
        record_movement(kind=StockMovement.Kind.RECEIPT, product=product, warehouse=warehouse, quantity=qty, user=vendor)


@pytest.fixture
def quote(vendor, hammer, cable, stocked):
    """10 martillos a 28.000 y 2 rollos de cable a 320.000."""
    q, _ = service.create_quote(user=vendor, client_uuid=uuid.uuid4(), customer_name="Don Jorge", lines=[
        {"product": hammer, "quantity": 10},
        {"product": cable, "quantity": 2, "unit": Unit.objects.get(code="rollo")},
    ])
    return q


def lines_of(quote):
    hammers = quote.lines.get(product__sku="MAR-16")
    rolls = quote.lines.get(product__sku="CAB-12")
    return hammers, rolls


def convert(quote, user, *parts, key=None):
    lines = [{"quote_line": line, "quantity": Decimal(q)} for line, q in parts] if parts else None
    order, _ = service.convert_quote(quote=quote, user=user, client_uuid=key or uuid.uuid4(), lines=lines)
    return order


def charge(order, cashier, shift, **quantities):
    """Cobra el pedido; con quantities={sku: cantidad} cobra solo eso (el cliente no se lleva todo)."""
    lines = None
    if quantities:
        lines = [{"order_line": order.lines.get(product__sku=sku), "quantity": Decimal(q)} for sku, q in quantities.items()]
    sale, _ = create_sale(user=cashier, shift=shift, order=order, lines=lines, client_uuid=uuid.uuid4(), payments=CASH)
    return sale


# --- convertir -------------------------------------------------------------------

def test_converts_everything_at_the_quoted_prices(vendor, quote, hammer):
    hammer.sale_price = Decimal("31000")  # el catálogo subió después de cotizar
    hammer.save()
    order = convert(quote, vendor)
    rows = sorted((l.product.sku, l.unit.code, l.quantity, l.unit_price, l.quote_line.quote_id) for l in order.lines.all())
    assert rows == [
        ("CAB-12", "rollo", Decimal("2.000"), Decimal("320000.00"), quote.pk),
        ("MAR-16", "und", Decimal("10.000"), Decimal("28000.00"), quote.pk),
    ]
    assert (order.total, order.salesperson, order.status) == (Decimal("920000.00"), vendor, Order.Status.PENDING)
    assert [service.remaining(line) for line in lines_of(quote)] == [0, 0]
    quote.refresh_from_db()
    assert quote.status == Quote.Status.VALID  # todavía no se cobra nada
    with pytest.raises(ValidationError, match=f"La cotización {quote.number} ya no tiene nada por convertir"):
        convert(quote, vendor)


def test_converts_by_parts_without_going_over(vendor, quote):
    hammers, rolls = lines_of(quote)
    first = convert(quote, vendor, (hammers, 4))
    assert [(l.product.sku, l.quantity) for l in first.lines.all()] == [("MAR-16", Decimal("4.000"))]
    convert(quote, vendor, (hammers, 3), (rolls, 1))
    assert [service.remaining(line) for line in lines_of(quote)] == [3, 1]
    with pytest.raises(ValidationError, match="MAR-16: quedan 3 und por convertir"):
        convert(quote, vendor, (hammers, 4))
    with pytest.raises(ValidationError, match="MAR-16: quedan 3 und por convertir"):  # repetida en la misma conversión
        convert(quote, vendor, (hammers, 2), (hammers, 2))
    with pytest.raises(ValidationError, match="CAB-12: la cantidad debe ser mayor que cero"):
        convert(quote, vendor, (rolls, 0))
    assert Order.objects.count() == 2


def test_a_line_from_another_quote_is_rejected(vendor, quote, hammer):
    other, _ = service.create_quote(user=vendor, client_uuid=uuid.uuid4(), customer_name="Otra", lines=[{"product": hammer, "quantity": 1}])
    with pytest.raises(ValidationError, match="no pertenece a esta cotización"):
        convert(quote, vendor, (other.lines.get(), 1))


def test_same_client_uuid_returns_the_same_order_even_when_nothing_is_left(vendor, quote):
    key = uuid.uuid4()
    first = convert(quote, vendor, key=key)
    again, created = service.convert_quote(quote=quote, user=vendor, client_uuid=key)
    assert (created, again.pk, Order.objects.count()) == (False, first.pk, 1)


@pytest.mark.parametrize("state, message", [
    ("expired", "está vencida. Duplícala para cotizar con los precios de hoy"),
    ("voided", "está anulada"),
    ("converted", "está convertida"),
])
def test_only_a_valid_quote_converts(vendor, quote, state, message):
    if state == "expired":
        Quote.objects.filter(pk=quote.pk).update(valid_until=business_date() - timedelta(days=1))
    elif state == "voided":
        service.void_quote(quote=quote, user=vendor, note="No")
    else:
        Quote.objects.filter(pk=quote.pk).update(status=Quote.Status.CONVERTED)
    with pytest.raises(ValidationError, match=message):
        convert(quote, vendor)
    assert not Order.objects.exists()


def test_a_product_no_longer_sold_cannot_be_converted(vendor, quote, hammer):
    hammer.is_active = False
    hammer.save()
    hammers, rolls = lines_of(quote)
    with pytest.raises(ValidationError, match="MAR-16 ya no está a la venta"):
        convert(quote, vendor)
    assert [(l.product.sku, l.quantity) for l in convert(quote, vendor, (rolls, 2)).lines.all()] == [("CAB-12", Decimal("2.000"))]


def test_an_ordinary_order_still_uses_the_catalog_price(vendor, hammer):
    order, _ = create_order(user=vendor, client_uuid=uuid.uuid4(), lines=[{"product": hammer, "quantity": 1}])
    line = order.lines.get()
    assert (line.unit_price, line.quote_line) == (Decimal("28000.00"), None)


# --- cobrar ------------------------------------------------------------------------

def test_charged_at_the_quoted_price_without_review(vendor, cashier, shift, warehouse, quote, hammer):
    hammer.sale_price = Decimal("31000")
    hammer.save()
    sale = charge(convert(quote, vendor), cashier, shift)
    assert (sale.total, sale.needs_review, sale.salesperson, sale.seller) == (Decimal("920000.00"), False, vendor, cashier)
    assert sale.lines.get(product=hammer).catalog_price == Decimal("31000.00")  # queda constancia del de hoy
    assert StockLevel.objects.get(product=hammer, warehouse=warehouse).quantity == 40
    quote.refresh_from_db()
    assert quote.status == Quote.Status.CONVERTED  # se cobró todo


def test_an_ordinary_order_with_another_price_still_goes_to_review(vendor, cashier, shift, hammer, stocked):
    order, _ = create_order(user=vendor, client_uuid=uuid.uuid4(), lines=[{"product": hammer, "quantity": 1}])
    hammer.sale_price = Decimal("31000")
    hammer.save()
    assert charge(order, cashier, shift).needs_review


def test_converted_only_when_everything_was_charged(vendor, cashier, shift, quote):
    hammers, rolls = lines_of(quote)
    charge(convert(quote, vendor, (hammers, 6), (rolls, 2)), cashier, shift, **{"MAR-16": 5, "CAB-12": 2})  # se llevó 5 de 6
    quote.refresh_from_db()
    assert quote.status == Quote.Status.VALID
    assert [service.remaining(line) for line in lines_of(quote)] == [5, 0]  # lo no cobrado vuelve a quedar

    pending = convert(quote, vendor, (hammers, 5))
    quote.refresh_from_db()
    assert quote.status == Quote.Status.VALID  # en un pedido pendiente no está cobrado
    cancel_order(order=pending, user=vendor)
    assert service.remaining(hammers) == 5  # cancelado: vuelve a quedar

    charge(convert(quote, vendor), cashier, shift)
    quote.refresh_from_db()
    assert quote.status == Quote.Status.CONVERTED
    assert [service.charged(line) for line in lines_of(quote)] == [10, 2]


def test_charging_one_of_two_orders_does_not_convert_it(vendor, cashier, shift, quote):
    hammers, rolls = lines_of(quote)
    convert(quote, vendor, (hammers, 10))  # pendiente
    charge(convert(quote, vendor, (rolls, 2)), cashier, shift)
    quote.refresh_from_db()
    assert quote.status == Quote.Status.VALID  # los martillos siguen en un pedido sin cobrar


def test_an_expired_order_frees_its_part(vendor, quote):
    hammers, _ = lines_of(quote)
    old = convert(quote, vendor, (hammers, 10))
    Order.objects.filter(pk=old.pk).update(business_date=business_date() - timedelta(days=1))
    assert service.remaining(hammers) == 10
    assert convert(quote, vendor, (hammers, 10)).lines.get().quantity == 10


# --- concurrencia (PostgreSQL) -------------------------------------------------------

@pytest.mark.skipif(connection.vendor == "sqlite", reason="SQLite no permite escrituras concurrentes")
@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_two_conversions_at_once_never_go_over(vendor, quote):  # pragma: no cover
    hammers, _ = lines_of(quote)
    errors = []

    def take():
        try:
            convert(quote, vendor, (hammers, 7))
        except ValidationError as exc:
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=take) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(errors) == 1
    assert service.remaining(hammers) == 3
