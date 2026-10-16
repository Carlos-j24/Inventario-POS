"""Spec 002, T1: modelos de pedido y vendedor de la venta."""
import datetime
import uuid
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.inventory.models import StockMovement
from apps.inventory.services import record_movement
from apps.sales.models import Order, OrderLine, business_date
from apps.sales.services import create_sale

pytestmark = pytest.mark.django_db
D = Decimal


@pytest.fixture
def vendor(make_user):
    return make_user("andres", "Ventas")


def make_order(vendor, code=4821, day=None, **extra):
    return Order.objects.create(
        code=code, business_date=day or business_date(), client_uuid=uuid.uuid4(),
        salesperson=vendor, total=D("0"), **extra,
    )


def test_order_starts_pending_today(vendor):
    order = make_order(vendor)
    assert order.status == Order.Status.PENDING
    assert order.business_date == business_date()
    assert order.effective_status() == Order.Status.PENDING


def test_code_is_unique_per_day(vendor):
    make_order(vendor, code=4821)
    with pytest.raises(IntegrityError), transaction.atomic():
        make_order(vendor, code=4821)
    # El mismo número otro día sí se puede: el código se reinicia cada día.
    make_order(vendor, code=4821, day=business_date() - datetime.timedelta(days=1))


@pytest.mark.parametrize("code", [999, 10000])
def test_code_has_four_digits(vendor, code):
    with pytest.raises(IntegrityError), transaction.atomic():
        make_order(vendor, code=code)


def test_code_validators_explain_the_rule(vendor):
    order = Order(code=999, client_uuid=uuid.uuid4(), salesperson=vendor, total=0)
    with pytest.raises(ValidationError) as exc:
        order.full_clean()
    assert "code" in exc.value.message_dict


def test_pending_order_from_yesterday_counts_as_expired(vendor):
    yesterday = business_date() - datetime.timedelta(days=1)
    order = make_order(vendor, day=yesterday)
    assert order.status == Order.Status.PENDING  # nadie lo ha tocado
    assert order.effective_status() == Order.Status.EXPIRED
    paid_or_cancelled = make_order(vendor, code=1234, day=yesterday, status=Order.Status.CANCELLED)
    assert paid_or_cancelled.effective_status() == Order.Status.CANCELLED


def test_paid_order_must_have_its_sale(vendor):
    with pytest.raises(IntegrityError), transaction.atomic():
        make_order(vendor, status=Order.Status.PAID)


def test_order_lines_keep_the_quoted_price(vendor, cable):
    order = make_order(vendor)
    OrderLine.objects.create(
        order=order, product=cable, unit=cable.base_unit, quantity=D("12.5"),
        unit_price=D("3200"), total=D("40000"),
    )
    cable.sale_price = D("3500")  # el catálogo cambia después
    cable.save()
    assert order.lines.get().unit_price == D("3200")


def test_direct_sale_is_sold_and_charged_by_the_cashier(make_user, shift, warehouse, hammer):
    cashier = make_user("laura", "Caja")
    record_movement(kind=StockMovement.Kind.RECEIPT, product=hammer, warehouse=warehouse, quantity=5, user=cashier)
    sale, _ = create_sale(
        user=cashier, shift=shift, client_uuid=uuid.uuid4(),
        lines=[{"product": hammer, "quantity": 1}], payments=[{"method": "CASH", "amount": D("28000")}],
    )
    assert sale.seller == cashier
    assert sale.salesperson == cashier


def test_business_date_uses_bogota_time_not_utc():
    # 03:00 UTC del 16 de octubre son las 22:00 del 15 en Bogotá: el pedido es del 15.
    moment = datetime.datetime(2026, 10, 16, 3, 0, tzinfo=datetime.timezone.utc)
    assert business_date(moment) == datetime.date(2026, 10, 15)
    assert business_date(moment + datetime.timedelta(hours=5)) == datetime.date(2026, 10, 16)
