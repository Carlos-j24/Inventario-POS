"""Órdenes de trabajo: cobro y entrega (spec 011, T3)."""
import datetime
import uuid
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import override_settings

from apps.cash.models import CashRegister
from apps.cash.services import open_shift
from apps.inventory.models import StockLevel, Warehouse
from apps.invoicing.models import NumberingResolution
from apps.reports.costs import margins_report
from apps.sales.models import Order, Sale, business_date
from apps.sales.orders import cancel_order
from apps.sales.returns import create_return, void_sale
from apps.sales.services import create_sale

from . import work_orders as svc
from .models import WorkOrder
from .test_work_orders import approved, clerk, events, labor, main, mechanic, moto, oil, order, stock  # noqa: F401

pytestmark = pytest.mark.django_db
Status = WorkOrder.Status
D = Decimal
CASH = [{"method": "CASH", "amount": D("10000000")}]


@pytest.fixture
def cashier(make_user):
    return make_user("laura", "Caja")


@pytest.fixture
def ready(order, clerk, mechanic, oil, labor):
    """Aceite ($32.000, salió de la bodega) y mano de obra ($25.000), aprobados; la orden está lista."""
    approved(order, clerk, mechanic, oil, labor)
    svc.take_part(line=order.lines.get(product=oil), user=mechanic)
    return svc.mark_ready(order=order, user=mechanic)


def charge(cashier, shift, sales_order, **extra):
    sale, _ = create_sale(user=cashier, shift=shift, order=sales_order, lines=None, payments=CASH, client_uuid=uuid.uuid4(), **extra)
    return sale


@pytest.fixture
def paid(ready, clerk, cashier, shift):
    return charge(cashier, shift, svc.send_to_till(order=ready, user=clerk))


# --- mandar a la caja --------------------------------------------------------------

def test_a_ready_order_goes_to_the_till_with_the_approved_prices(ready, clerk, oil, labor):
    sales_order = svc.send_to_till(order=ready, user=clerk)
    assert (sales_order.status, sales_order.work_order, sales_order.salesperson, sales_order.total) == (
        Order.Status.PENDING, ready, clerk, D("57000.00"))
    assert 1000 <= sales_order.code <= 9999 and sales_order.business_date == business_date()
    lines = {line.product: line for line in sales_order.lines.all()}
    assert (lines[oil].unit_price, lines[oil].quantity, lines[oil].unit) == (D("32000.00"), 1, oil.base_unit)
    assert lines[labor].unit_price == D("25000.00")  # el del catálogo es 0: va el aprobado
    assert {line.work_order_line for line in lines.values()} == set(ready.lines.all())
    assert events(ready)[-1] == (Status.READY, "diana", f"A la caja: pedido {sales_order.code}")
    assert svc.till_order(ready) == sales_order


def test_only_reception_sends_a_ready_order_once(order, ready, clerk, mechanic):
    with pytest.raises(PermissionDenied):
        svc.send_to_till(order=ready, user=mechanic)
    first = svc.send_to_till(order=ready, user=clerk)
    with pytest.raises(ValidationError, match=f"ya está en la caja: pedido {first.code}"):
        svc.send_to_till(order=ready, user=clerk)
    cancel_order(order=first, user=clerk)  # la caja lo canceló: se manda otra vez
    second = svc.send_to_till(order=ready, user=clerk)
    Order.objects.filter(pk=second.pk).update(business_date=business_date() - datetime.timedelta(days=1))
    assert svc.till_order(ready) is None  # el de ayer se venció
    assert svc.send_to_till(order=ready, user=clerk) not in (first, second)


def test_an_order_that_is_not_ready_does_not_go_to_the_till(order, clerk, mechanic, oil, labor):
    approved(order, clerk, mechanic, oil, labor)
    with pytest.raises(ValidationError, match="está en reparación: no se puede mandar a la caja"):
        svc.send_to_till(order=order, user=clerk)


def test_an_order_with_nothing_to_charge_does_not_go_to_the_till(order, clerk, mechanic, oil, labor):
    approved(order, clerk, mechanic, oil, labor)
    line = svc.take_part(line=order.lines.get(product=oil), user=mechanic)
    svc.return_part(line=line, user=mechanic)
    svc.remove_line(line=order.lines.get(product=labor), user=mechanic)
    svc.mark_ready(order=order, user=mechanic)
    with pytest.raises(ValidationError, match="No hay nada que cobrar"):
        svc.send_to_till(order=order, user=clerk)


# --- cobro -------------------------------------------------------------------------

def test_the_till_charges_it_without_taking_the_parts_again(ready, clerk, cashier, shift, oil, labor):
    sales_order = svc.send_to_till(order=ready, user=clerk)
    sale = charge(cashier, shift, sales_order)
    assert (sale.total, sale.salesperson, sale.seller, sale.needs_review) == (D("57000.00"), clerk, cashier, False)
    assert stock(oil) == 9  # salió una sola vez, con la orden
    oil_line = ready.lines.get(product=oil)
    sold = sale.lines.get(product=oil)
    assert sold.movement == oil_line.movement
    sold.movement.refresh_from_db()
    assert sold.movement.reference == f"Orden {ready.number}"
    assert sale.lines.get(product=labor).movement is None
    sales_order.refresh_from_db()
    assert (sales_order.status, svc.paid_sale(ready)) == (Order.Status.PAID, sale)
    assert svc.till_order(ready) is None
    with pytest.raises(ValidationError, match="ya está cobrada"):
        svc.send_to_till(order=ready, user=clerk)


def test_the_margin_uses_the_cost_the_part_left_with(paid, oil):
    row = next(r for r in margins_report(business_date(), business_date())["rows"] if r["sku"] == oil.sku)
    assert row["cost"] == "21000.00"


def test_a_work_order_is_charged_in_full(ready, clerk, cashier, shift):
    sales_order = svc.send_to_till(order=ready, user=clerk)
    with pytest.raises(ValidationError, match="se cobra completa"):
        create_sale(user=cashier, shift=shift, order=sales_order, payments=CASH, client_uuid=uuid.uuid4(),
                    lines=[{"order_line": sales_order.lines.first(), "quantity": 1}])


@override_settings(INVOICING_ENABLED=True)
def test_the_document_goes_to_the_customer_of_the_order(ready, clerk, cashier, shift, register, client_co):
    common = {"register": register, "number": "18764", "issued_on": datetime.date(2026, 1, 1),
              "valid_from": datetime.date(2026, 1, 1), "valid_until": datetime.date(2027, 12, 31), "range_from": 1, "range_to": 50}
    NumberingResolution.objects.create(document_type="POS", prefix="CJ1", **common)
    first = charge(cashier, shift, svc.send_to_till(order=ready, user=clerk))
    assert first.fiscal_documents.get().customer == ready.customer
    void_sale(sale=first, user=cashier, reason="Otro cliente")
    second = charge(cashier, shift, svc.send_to_till(order=ready, user=clerk), customer=client_co)
    assert second.fiscal_documents.get().customer == client_co  # si la caja dice otro, ese


@pytest.fixture
def client_co(db):
    from apps.customers.models import Customer

    return Customer.objects.create(id_type="31", id_number="800197268", check_digit="4", person_type="1", name="Constructora SAS")


# --- entrega -----------------------------------------------------------------------

def test_delivery_needs_the_order_paid(ready, clerk, mechanic, cashier, shift):
    with pytest.raises(ValidationError, match="no está cobrada"):
        svc.deliver(order=ready, user=clerk)
    sales_order = svc.send_to_till(order=ready, user=clerk)
    with pytest.raises(ValidationError, match="no está cobrada"):
        svc.deliver(order=ready, user=clerk)
    charge(cashier, shift, sales_order)
    with pytest.raises(PermissionDenied):
        svc.deliver(order=ready, user=mechanic)
    svc.deliver(order=ready, user=clerk)
    ready.refresh_from_db()
    assert (ready.status, ready.mileage_out) == (Status.DELIVERED, 15400)
    assert events(ready)[-1] == (Status.DELIVERED, "diana", "")
    with pytest.raises(ValidationError, match="está entregada: no se puede entregar"):
        svc.deliver(order=ready, user=clerk)


def test_delivery_records_the_mileage_out_if_it_changed(paid, ready, clerk, moto):
    with pytest.raises(ValidationError):
        svc.deliver(order=ready, user=clerk, mileage=15300)  # baja sin nota
    svc.deliver(order=ready, user=clerk, mileage=15412, mileage_note="Prueba de ruta")
    ready.refresh_from_db()
    moto.refresh_from_db()
    reading = moto.mileage_readings.first()
    assert (ready.mileage_out, moto.mileage, reading.mileage, reading.note) == (15412, 15412, 15412, "Prueba de ruta")


def test_delivery_with_the_same_mileage_adds_no_reading(paid, ready, clerk, moto):
    readings = moto.mileage_readings.count()
    svc.deliver(order=ready, user=clerk, mileage=15400)
    ready.refresh_from_db()
    assert (ready.mileage_out, moto.mileage_readings.count()) == (15400, readings)


def test_an_order_in_repair_is_not_delivered(order, clerk):
    with pytest.raises(ValidationError, match="está recibida: no se puede entregar"):
        svc.deliver(order=order, user=clerk)


# --- anular la venta ---------------------------------------------------------------

def test_voiding_the_sale_leaves_the_order_ready_to_charge_again(paid, ready, clerk, cashier, shift, oil):
    void_sale(sale=paid, user=cashier, reason="Se cobró con el medio de pago equivocado")
    assert stock(oil) == 9  # el aceite sigue puesto en la moto
    ready.refresh_from_db()
    assert ready.status == Status.READY
    assert events(ready)[-1] == (Status.READY, "laura", f"Se anuló la venta {paid.number}")
    assert svc.paid_sale(ready) is None
    with pytest.raises(ValidationError, match="no está cobrada"):
        svc.deliver(order=ready, user=clerk)
    again = charge(cashier, shift, svc.send_to_till(order=ready, user=clerk))
    assert again.lines.get(product=oil).movement == paid.lines.get(product=oil).movement
    assert stock(oil) == 9
    svc.deliver(order=ready, user=clerk)


def test_a_returned_part_goes_back_to_the_warehouse_it_left(ready, clerk, cashier, make_user, main, oil):
    branch = Warehouse.objects.create(code="SUC", name="Sucursal")
    register = CashRegister.objects.create(code="CAJA2", name="Caja 2", warehouse=branch)
    shift = open_shift(register=register, user=make_user("apertura2", "Caja"), opening_float=D("0"))
    sale = charge(cashier, shift, svc.send_to_till(order=ready, user=clerk))
    create_return(sale=sale, user=cashier, shift=shift, lines=[{"sale_line": sale.lines.get(product=oil), "quantity": 1}],
                  refund_method="CASH", reason="No le sirvió", client_uuid=uuid.uuid4())
    assert StockLevel.objects.get(product=oil, warehouse=main).quantity == 10
    assert not StockLevel.objects.filter(product=oil, warehouse=branch).exists()


def test_voiding_an_ordinary_sale_still_returns_the_stock(cashier, shift, main, oil):
    sale, _ = create_sale(user=cashier, shift=shift, lines=[{"product": oil, "quantity": 2}], payments=CASH, client_uuid=uuid.uuid4())
    assert stock(oil) == 8
    assert sale.lines.get().movement.reference == f"Venta {sale.number}"
    sale = void_sale(sale=sale, user=cashier, reason="Error")
    assert stock(oil) == 10
    assert sale.status == Sale.Status.VOIDED


# --- cancelar ----------------------------------------------------------------------

def test_cancelling_takes_its_order_out_of_the_till(ready, clerk, oil):
    sales_order = svc.send_to_till(order=ready, user=clerk)
    svc.cancel(order=ready, user=clerk, reason="El cliente no volvió")
    sales_order.refresh_from_db()
    assert (sales_order.status, sales_order.cancelled_by) == (Order.Status.CANCELLED, clerk)
    assert sales_order.cancelled_at is not None
    assert stock(oil) == 10


def test_a_paid_order_is_not_cancelled(paid, ready, clerk, oil):
    with pytest.raises(ValidationError, match=f"anula la venta {paid.number} primero"):
        svc.cancel(order=ready, user=clerk, reason="Ya no")
    ready.refresh_from_db()
    assert ready.status == Status.READY
    assert stock(oil) == 9
