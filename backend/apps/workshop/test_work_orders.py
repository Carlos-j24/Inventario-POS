"""Órdenes de trabajo, los servicios (spec 011, T2)."""
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from apps.catalog.models import Category, Product, Unit
from apps.customers.models import Customer
from apps.inventory.models import StockLevel, StockMovement, Warehouse
from apps.inventory.services import InsufficientStock, record_movement

from . import work_orders as svc
from .models import MileageReading, WorkOrder, WorkOrderLine
from .services import register_motorcycle

pytestmark = pytest.mark.django_db
Status = WorkOrder.Status
D = Decimal


@pytest.fixture
def clerk(make_user):
    return make_user("diana", "Recepción de taller")


@pytest.fixture
def mechanic(make_user):
    return make_user("carlos", "Mecánico")


@pytest.fixture
def other(make_user):
    return make_user("pablo", "Mecánico")


@pytest.fixture
def main(warehouse):
    Warehouse.objects.filter(pk=warehouse.pk).update(is_default=True)
    warehouse.refresh_from_db()
    return warehouse


@pytest.fixture
def moto(clerk):
    owner = Customer.objects.create(id_type="13", id_number="79123456", name="Jorge Ramírez", phone="3001234567")
    return register_motorcycle(user=clerk, owner=owner, plate="XYZ12A", brand="Bajaj", model="Boxer CT 100", mileage=15200)


def part(sku, name, price, stock, main, user, cost="10000", **extra):
    product = Product.objects.create(
        sku=sku, name=name, category=Category.objects.get_or_create(name="Repuestos")[0],
        base_unit=Unit.objects.get(code="und"), sale_price=D(price), **extra,
    )
    if stock:
        record_movement(kind=StockMovement.Kind.RECEIPT, product=product, warehouse=main, quantity=stock, user=user, unit_cost=cost)
    return product


@pytest.fixture
def oil(main, clerk):
    return part("ACE-20W50", "Aceite 20W50", "32000", 10, main, clerk, cost="21000")


@pytest.fixture
def pads(main, clerk):
    return part("PAS-DEL", "Pastillas delanteras", "28000", 5, main, clerk, cost="15500")


@pytest.fixture
def labor(db):
    return Product.objects.create(
        sku="MO-TALLER", name="Mano de obra", category=Category.objects.get_or_create(name="Mano de obra")[0],
        base_unit=Unit.objects.get(code="und"), sale_price=D("0"), is_service=True,
    )


def stock(product):
    return StockLevel.objects.get(product=product).quantity


@pytest.fixture
def order(moto, clerk, mechanic):
    return svc.receive_order(user=clerk, motorcycle=moto, mileage=15400, request="Cambio de aceite y revisar frenos",
                             condition="Rayón en el tanque; deja el casco", mechanic=mechanic)


def approved(order, clerk, mechanic, oil, labor):
    """Aceite y mano de obra de $25.000, aprobados por llamada."""
    svc.add_line(order=order, user=mechanic, product=oil, quantity=1)
    work = svc.add_line(order=order, user=mechanic, product=labor, quantity=1)
    svc.set_price(line=work, user=clerk, unit_price=D("25000"))
    svc.send_for_approval(order=order, user=mechanic)
    return svc.approve(order=order, user=clerk, approved_by="Jorge Ramírez", channel="PHONE")


def events(order):
    return [(e.status, e.user.username, e.note) for e in order.events.all()]


# --- recibir y asignar -------------------------------------------------------------

def test_receiving_updates_the_motorcycle_and_opens_the_order(order, moto, clerk, mechanic):
    moto.refresh_from_db()
    assert (moto.mileage, moto.mileage_readings.first().mileage) == (15400, 15400)
    assert (order.status, order.customer, order.mileage_in, order.mechanic, order.received_by) == (Status.RECEIVED, moto.owner, 15400, mechanic, clerk)
    assert (order.request, order.condition) == ("Cambio de aceite y revisar frenos", "Rayón en el tanque; deja el casco")
    assert events(order) == [(Status.RECEIVED, "diana", "")]


def test_receiving_rules(moto, clerk, mechanic):
    with pytest.raises(PermissionDenied):
        svc.receive_order(user=mechanic, motorcycle=moto, mileage=15400, request="Aceite")
    with pytest.raises(ValidationError, match="lo que pide el cliente"):
        svc.receive_order(user=clerk, motorcycle=moto, mileage=15400, request="  ")
    with pytest.raises(ValidationError, match="no es un mecánico activo"):
        svc.receive_order(user=clerk, motorcycle=moto, mileage=15400, request="Aceite", mechanic=clerk)
    with pytest.raises(ValidationError, match="solo sube"):
        svc.receive_order(user=clerk, motorcycle=moto, mileage=100, request="Aceite")
    readings = MileageReading.objects.count()
    order = svc.receive_order(user=clerk, motorcycle=moto, mileage=15200, request="Aceite")  # el mismo: no hay lectura nueva
    assert MileageReading.objects.count() == readings
    with pytest.raises(ValidationError, match="ya tiene una orden de trabajo abierta"):
        svc.receive_order(user=clerk, motorcycle=moto, mileage=15200, request="Otra")
    svc.cancel(order=order, user=clerk, reason="Error")
    moto.is_active = False
    moto.save()
    with pytest.raises(ValidationError, match="inactiva"):
        svc.receive_order(user=clerk, motorcycle=moto, mileage=15200, request="Aceite")


def test_a_lower_mileage_with_a_note_is_accepted(moto, clerk):
    svc.receive_order(user=clerk, motorcycle=moto, mileage=120, request="Revisión", mileage_note="Cambio de tablero")
    moto.refresh_from_db()
    assert (moto.mileage, moto.mileage_readings.first().note) == (120, "Cambio de tablero")


def test_only_reception_assigns_a_mechanic(order, clerk, mechanic, other):
    with pytest.raises(PermissionDenied):
        svc.assign_mechanic(order=order, mechanic=other, user=mechanic)
    assert svc.assign_mechanic(order=order, mechanic=other, user=clerk).mechanic == other
    with pytest.raises(ValidationError, match="no es un mecánico"):
        svc.assign_mechanic(order=order, mechanic=clerk, user=clerk)
    other.is_active = False
    other.save()
    with pytest.raises(ValidationError, match="no es un mecánico activo"):
        svc.assign_mechanic(order=order, mechanic=other, user=clerk)


# --- diagnóstico y líneas ----------------------------------------------------------

def test_only_the_assigned_mechanic_or_reception_works_on_the_order(order, clerk, mechanic, other, oil):
    assert svc.diagnose(order=order, user=mechanic, diagnosis=" Pastillas gastadas ").diagnosis == "Pastillas gastadas"
    assert svc.diagnose(order=order, user=clerk, diagnosis="Pastillas al 10 %").diagnosis == "Pastillas al 10 %"
    for action in (lambda: svc.diagnose(order=order, user=other, diagnosis="x"),
                   lambda: svc.add_line(order=order, user=other, product=oil, quantity=1),
                   lambda: svc.send_for_approval(order=order, user=other)):
        with pytest.raises(PermissionDenied, match="no está asignada a ti"):
            action()


def test_parts_go_at_the_catalog_price_and_the_mechanic_sets_no_prices(order, clerk, mechanic, oil, labor):
    line = svc.add_line(order=order, user=mechanic, product=oil, quantity=2)
    assert (line.unit_price, line.is_service, line.approved, line.added_by) == (D("32000"), False, False, mechanic)
    with pytest.raises(ValidationError, match="precio del catálogo"):
        svc.add_line(order=order, user=clerk, product=oil, quantity=1, unit_price=D("1"))
    with pytest.raises(PermissionDenied):
        svc.add_line(order=order, user=mechanic, product=labor, quantity=1, unit_price=D("25000"))
    work = svc.add_line(order=order, user=clerk, product=labor, quantity=1, unit_price=D("25000"))
    assert (work.unit_price, work.is_service) == (D("25000"), True)
    with pytest.raises(PermissionDenied):
        svc.set_price(line=work, user=mechanic, unit_price=D("30000"))
    with pytest.raises(ValidationError, match="precio del catálogo"):
        svc.set_price(line=line, user=clerk, unit_price=D("1"))
    with pytest.raises(ValidationError, match="negativo"):
        svc.set_price(line=work, user=clerk, unit_price=D("-1"))


def test_what_can_be_added(order, mechanic, oil, main, clerk):
    with pytest.raises(ValidationError, match="positiva"):
        svc.add_line(order=order, user=mechanic, product=oil, quantity=0)
    with pytest.raises(ValidationError, match="no se vende fraccionado"):
        svc.add_line(order=order, user=mechanic, product=oil, quantity=D("1.5"))
    cable = part("CAB-16", "Cable 16", "2800", 50, main, clerk, allows_fractions=True)
    assert svc.add_line(order=order, user=mechanic, product=cable, quantity=D("1.5")).quantity == D("1.5")
    for off in (part("X-1", "Inactivo", "1", 0, main, clerk, is_active=False),
                part("X-2", "Sin precio", "0", 0, main, clerk, price_pending=True, is_active=False)):
        with pytest.raises(ValidationError, match="no está a la venta"):
            svc.add_line(order=order, user=mechanic, product=off, quantity=1)


# --- aprobación ---------------------------------------------------------------------

def test_approval_flow(order, clerk, mechanic, oil, labor):
    with pytest.raises(ValidationError, match="No hay nada por aprobar"):
        svc.send_for_approval(order=order, user=mechanic)
    svc.add_line(order=order, user=mechanic, product=oil, quantity=1)
    work = svc.add_line(order=order, user=mechanic, product=labor, quantity=1)
    assert svc.send_for_approval(order=order, user=mechanic).status == Status.AWAITING_APPROVAL
    with pytest.raises(ValidationError, match="Ponle precio a Mano de obra"):
        svc.approve(order=order, user=clerk, approved_by="Jorge", channel="PHONE")
    svc.set_price(line=work, user=clerk, unit_price=D("25000"))
    with pytest.raises(PermissionDenied):
        svc.approve(order=order, user=mechanic, approved_by="Jorge", channel="PHONE")
    with pytest.raises(ValidationError, match="quién aprobó"):
        svc.approve(order=order, user=clerk, approved_by=" ", channel="PHONE")
    with pytest.raises(ValidationError, match="cómo aprobó"):
        svc.approve(order=order, user=clerk, approved_by="Jorge", channel="EMAIL")
    order = svc.approve(order=order, user=clerk, approved_by=" Jorge Ramírez ", channel="PHONE")
    approval = order.approvals.get()
    assert (order.status, approval.approved_by, approval.channel, approval.total, approval.recorded_by) == (
        Status.IN_REPAIR, "Jorge Ramírez", "PHONE", D("57000.00"), clerk,
    )
    assert not svc.pending_lines(order).exists()
    with pytest.raises(ValidationError, match="ya aprobó ese precio"):
        svc.set_price(line=work, user=clerk, unit_price=D("30000"))
    with pytest.raises(ValidationError, match="No hay nada por aprobar"):
        svc.approve(order=order, user=clerk, approved_by="Jorge", channel="PHONE")
    assert events(order) == [
        (Status.RECEIVED, "diana", ""), (Status.AWAITING_APPROVAL, "carlos", ""), (Status.IN_REPAIR, "diana", "Aprobó Jorge Ramírez"),
    ]


def test_reception_can_approve_without_sending_first(order, clerk, mechanic, oil, labor):
    assert approved(order, clerk, mechanic, oil, labor).status == Status.IN_REPAIR
    order.refresh_from_db()
    svc.add_line(order=order, user=clerk, product=oil, quantity=1)
    assert svc.approve(order=order, user=clerk, approved_by="Jorge", channel="IN_PERSON").approvals.first().total == D("89000.00")


# --- repuestos ---------------------------------------------------------------------

def test_approved_parts_leave_the_main_warehouse(order, clerk, mechanic, oil, labor, main):
    approved(order, clerk, mechanic, oil, labor)
    oil_line = order.lines.get(product=oil)
    line = svc.take_part(line=oil_line, user=mechanic)
    assert (line.movement.kind, line.movement.warehouse, line.movement.reference, line.movement.quantity) == (
        StockMovement.Kind.WORKSHOP_OUT, main, f"Orden {order.number}", D("-1.000"),
    )
    assert stock(oil) == 9
    with pytest.raises(ValidationError, match="ya salió"):
        svc.take_part(line=oil_line, user=mechanic)
    with pytest.raises(ValidationError, match="La mano de obra no sale"):
        svc.take_part(line=order.lines.get(product=labor), user=mechanic)


def test_what_is_added_after_approving_waits_for_a_new_approval(order, clerk, mechanic, oil, labor, pads):
    approved(order, clerk, mechanic, oil, labor)
    extra = svc.add_line(order=order, user=mechanic, product=pads, quantity=1)
    with pytest.raises(ValidationError, match="todavía no aprueba"):
        svc.take_part(line=extra, user=mechanic)
    svc.take_part(line=order.lines.get(product=oil), user=mechanic)
    with pytest.raises(ValidationError, match="Hay cambios sin aprobar"):
        svc.mark_ready(order=order, user=mechanic)
    svc.remove_line(line=extra, user=mechanic)  # el cliente no quiso las pastillas
    assert svc.mark_ready(order=order, user=mechanic).status == Status.READY
    assert stock(pads) == 5


def test_parts_are_taken_only_while_repairing_and_with_stock(order, clerk, mechanic, oil, labor, main):
    svc.add_line(order=order, user=mechanic, product=oil, quantity=1)
    WorkOrderLine.objects.filter(work_order=order).update(approved=True)  # aprobado pero la orden sigue recibida
    with pytest.raises(ValidationError, match="no se puede sacar repuestos"):
        svc.take_part(line=order.lines.get(), user=mechanic)
    order.refresh_from_db()
    big = svc.add_line(order=order, user=mechanic, product=oil, quantity=20)
    svc.send_for_approval(order=order, user=mechanic)
    svc.approve(order=order, user=clerk, approved_by="Jorge", channel="PHONE")
    with pytest.raises(InsufficientStock):
        svc.take_part(line=big, user=mechanic)
    Warehouse.objects.filter(pk=main.pk).update(is_default=False)
    with pytest.raises(ValidationError, match="No hay bodega principal"):
        svc.take_part(line=order.lines.first(), user=mechanic)


def test_an_unused_part_goes_back_at_its_cost_and_is_not_charged(order, clerk, mechanic, oil, labor):
    approved(order, clerk, mechanic, oil, labor)
    oil_line = order.lines.get(product=oil)
    with pytest.raises(ValidationError, match="no ha salido"):
        svc.return_part(line=oil_line, user=mechanic)
    oil_line = svc.take_part(line=oil_line, user=mechanic)
    with pytest.raises(ValidationError, match="regrésalo en vez de quitarlo"):
        svc.remove_line(line=oil_line, user=mechanic)
    record_movement(kind=StockMovement.Kind.RECEIPT, product=oil, warehouse=oil_line.movement.warehouse, quantity=1, user=clerk, unit_cost="30000")
    back = svc.return_part(line=oil_line, user=mechanic).returned_movement
    assert (back.kind, back.quantity, back.unit_cost, back.reference) == (StockMovement.Kind.WORKSHOP_RETURN, D("1.000"), D("21000.0000"), f"Orden {order.number}")
    assert stock(oil) == 11
    with pytest.raises(ValidationError, match="ya volvió"):
        svc.return_part(line=oil_line, user=mechanic)
    assert svc.charged_total(order) == D("25000.00")  # solo la mano de obra


def test_ready_needs_every_approved_part_on_the_motorcycle(order, clerk, mechanic, oil, labor):
    approved(order, clerk, mechanic, oil, labor)
    with pytest.raises(ValidationError, match="Aceite 20W50 está aprobado pero no ha salido"):
        svc.mark_ready(order=order, user=mechanic)
    svc.take_part(line=order.lines.get(product=oil), user=mechanic)
    order = svc.mark_ready(order=order, user=mechanic)
    assert events(order)[-1] == (Status.READY, "carlos", "")
    for action in (lambda: svc.add_line(order=order, user=mechanic, product=oil, quantity=1),
                   lambda: svc.diagnose(order=order, user=mechanic, diagnosis="x"),
                   lambda: svc.mark_ready(order=order, user=mechanic)):
        with pytest.raises(ValidationError, match="está lista"):
            action()


def test_an_approved_part_that_was_not_used_can_be_removed(order, clerk, mechanic, oil, labor):
    approved(order, clerk, mechanic, oil, labor)
    svc.remove_line(line=order.lines.get(product=oil), user=mechanic)
    assert svc.mark_ready(order=order, user=mechanic).status == Status.READY
    assert svc.charged_total(order) == D("25000.00")


# --- cancelar ----------------------------------------------------------------------

def test_cancelling_brings_back_what_left(order, clerk, mechanic, oil, labor, pads):
    approved(order, clerk, mechanic, oil, labor)
    svc.add_line(order=order, user=clerk, product=pads, quantity=2)
    svc.approve(order=order, user=clerk, approved_by="Jorge", channel="IN_PERSON")
    svc.take_part(line=order.lines.get(product=oil), user=mechanic)
    pads_line = svc.take_part(line=order.lines.get(product=pads), user=mechanic)
    svc.return_part(line=pads_line, user=mechanic)  # ya había vuelto: no vuelve dos veces
    with pytest.raises(PermissionDenied):
        svc.cancel(order=order, user=mechanic, reason="x")
    with pytest.raises(ValidationError, match="por qué se cancela"):
        svc.cancel(order=order, user=clerk, reason=" ")
    order = svc.cancel(order=order, user=clerk, reason="El cliente se llevó la moto sin arreglar")
    assert (stock(oil), stock(pads)) == (10, 5)
    assert order.lines.get(product=oil).returned_movement.kind == StockMovement.Kind.WORKSHOP_RETURN
    assert events(order)[-1] == (Status.CANCELLED, "diana", "El cliente se llevó la moto sin arreglar")
    with pytest.raises(ValidationError, match="está cancelada"):
        svc.cancel(order=order, user=clerk, reason="Otra vez")
    with pytest.raises(ValidationError, match="está cancelada"):
        svc.assign_mechanic(order=order, mechanic=mechanic, user=clerk)


def test_a_cancelled_order_with_pending_changes_stays_cancelled(order, clerk, mechanic, oil, labor):
    svc.add_line(order=order, user=mechanic, product=oil, quantity=1)
    work = svc.add_line(order=order, user=mechanic, product=labor, quantity=1)
    order = svc.cancel(order=order, user=clerk, reason="No volvió")
    for action in (lambda: svc.approve(order=order, user=clerk, approved_by="Jorge", channel="PHONE"),
                   lambda: svc.set_price(line=work, user=clerk, unit_price=D("25000")),
                   lambda: svc.remove_line(line=work, user=clerk)):
        with pytest.raises(ValidationError, match="está cancelada"):
            action()
    order.refresh_from_db()
    assert (order.status, order.lines.count()) == (Status.CANCELLED, 2)


def test_a_ready_order_keeps_its_parts(order, clerk, mechanic, oil, labor):
    approved(order, clerk, mechanic, oil, labor)
    taken = svc.take_part(line=order.lines.get(product=oil), user=mechanic)
    svc.mark_ready(order=order, user=mechanic)
    with pytest.raises(ValidationError, match="está lista"):
        svc.return_part(line=taken, user=mechanic)
    assert stock(oil) == 9


def test_a_delivered_order_cannot_be_cancelled(order, clerk):
    WorkOrder.objects.filter(pk=order.pk).update(status=Status.DELIVERED)
    with pytest.raises(ValidationError, match="está entregada"):
        svc.cancel(order=order, user=clerk, reason="x")
