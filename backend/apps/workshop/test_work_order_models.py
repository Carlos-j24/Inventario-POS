"""Órdenes de trabajo, el modelo (spec 011, T1)."""
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import Client

from apps.accounts.models import Role, User
from apps.catalog.models import Category, Product, Unit
from apps.customers.models import Customer
from apps.inventory.models import StockLevel, StockMovement
from apps.inventory.services import record_movement

from .models import WorkOrder, WorkOrderApproval, WorkOrderEvent, WorkOrderLine
from .services import register_motorcycle

pytestmark = pytest.mark.django_db
Status = WorkOrder.Status


@pytest.fixture
def clerk(make_user):
    return make_user("recepcion", "Recepción de taller")


@pytest.fixture
def moto(clerk):
    owner = Customer.objects.create(id_type="13", id_number="79123456", name="Jorge Ramírez", phone="3001234567")
    return register_motorcycle(user=clerk, owner=owner, plate="XYZ12A", brand="Bajaj", model="Boxer CT 100", mileage=15200)


@pytest.fixture
def oil(clerk, warehouse):
    product = Product.objects.create(
        sku="ACE-20W50", name="Aceite 20W50", category=Category.objects.create(name="Lubricantes"),
        base_unit=Unit.objects.get(code="und"), sale_price=Decimal("32000"),
    )
    record_movement(kind=StockMovement.Kind.RECEIPT, product=product, warehouse=warehouse, quantity=10, user=clerk, unit_cost="21000")
    return product


@pytest.fixture
def labor(db):
    return Product.objects.create(
        sku="MO-MANT", name="Mano de obra mantenimiento", category=Category.objects.create(name="Mano de obra"),
        base_unit=Unit.objects.get(code="und"), sale_price=Decimal("0"), is_service=True,
    )


def receive(moto, clerk, **extra):
    return WorkOrder.objects.create(motorcycle=moto, customer=moto.owner, mileage_in=15400, request="Cambio de aceite",
                                    received_by=clerk, **extra)


def line(order, product, clerk, **extra):
    data = {"work_order": order, "product": product, "is_service": product.is_service, "quantity": 1,
            "unit_price": product.sale_price, "added_by": clerk, **extra}
    return WorkOrderLine.objects.create(**data)


def take(product, warehouse, clerk, kind=StockMovement.Kind.WORKSHOP_OUT, **extra):
    movement, _ = record_movement(kind=kind, product=product, warehouse=warehouse, quantity=1, user=clerk, reference="OT", **extra)
    return movement


# --- permiso y rol -----------------------------------------------------------------

def test_the_mechanic_role_only_repairs_and_the_administrator_too():
    mechanic = Role.objects.get(name="Mecánico")
    assert [p.code for p in mechanic.permissions.all()] == ["workshop.repair"]
    assert Role.objects.get(name="Administrador").permissions.filter(code="workshop.repair").exists()
    assert not Role.objects.get(name="Recepción de taller").permissions.filter(code="workshop.repair").exists()


# --- la orden ----------------------------------------------------------------------

def test_a_new_order_is_received_and_numbered(moto, clerk):
    order = receive(moto, clerk, condition="Rayón en el tanque; deja el casco")
    assert (order.status, order.number, order.customer, order.mechanic) == (Status.RECEIVED, f"OT-{order.pk:06d}", moto.owner, None)
    assert str(order) == f"{order.number} · XYZ12A · Bajaj Boxer CT 100"


def test_one_open_order_per_motorcycle(moto, clerk):
    first = receive(moto, clerk)
    for status in (Status.RECEIVED, Status.AWAITING_APPROVAL, Status.IN_REPAIR, Status.READY):
        WorkOrder.objects.filter(pk=first.pk).update(status=status)
        with pytest.raises(IntegrityError), transaction.atomic():
            receive(moto, clerk)
    with pytest.raises(ValidationError, match="ya tiene una orden de trabajo abierta"):
        WorkOrder(motorcycle=moto, customer=moto.owner, mileage_in=1, request="x", received_by=clerk).validate_constraints()
    for status in (Status.DELIVERED, Status.CANCELLED):  # cerrada: puede volver a entrar
        WorkOrder.objects.filter(pk=first.pk).update(status=status)
        receive(moto, clerk).delete()
    assert list(WorkOrder.OPEN) == [Status.RECEIVED, Status.AWAITING_APPROVAL, Status.IN_REPAIR, Status.READY]


# --- líneas ------------------------------------------------------------------------

def test_line_total(moto, clerk, oil):
    assert line(receive(moto, clerk), oil, clerk, quantity=Decimal("1.5"), unit_price=Decimal("32000.33")).total == Decimal("48000.50")


def test_only_approved_parts_leave_the_warehouse(moto, clerk, oil, labor, warehouse):
    order = receive(moto, clerk)
    with pytest.raises(IntegrityError), transaction.atomic():
        line(order, oil, clerk, movement=take(oil, warehouse, clerk))  # sin aprobar
    with pytest.raises(IntegrityError), transaction.atomic():
        line(order, labor, clerk, approved=True, movement=take(oil, warehouse, clerk))  # la mano de obra no sale
    part = line(order, oil, clerk, approved=True, movement=take(oil, warehouse, clerk))
    assert part.movement.work_order_line == part


def test_only_what_left_comes_back(moto, clerk, oil, warehouse):
    order = receive(moto, clerk)
    back = take(oil, warehouse, clerk, kind=StockMovement.Kind.WORKSHOP_RETURN)
    with pytest.raises(IntegrityError), transaction.atomic():
        line(order, oil, clerk, approved=True, returned_movement=back)
    part = line(order, oil, clerk, approved=True, movement=take(oil, warehouse, clerk), returned_movement=back)
    assert part.returned_movement.work_order_return == part


# --- movimientos nuevos ------------------------------------------------------------

def test_workshop_movements_take_and_bring_back_stock(clerk, oil, warehouse):
    out = take(oil, warehouse, clerk)
    assert (out.quantity, out.balance_after, out.unit_cost, out.get_kind_display()) == (
        Decimal("-1.000"), Decimal("9.000"), Decimal("21000.0000"), "Salida a orden de trabajo",
    )
    back = take(oil, warehouse, clerk, kind=StockMovement.Kind.WORKSHOP_RETURN, unit_cost=out.unit_cost)
    assert (back.quantity, back.balance_after, back.get_kind_display()) == (Decimal("1.000"), Decimal("10.000"), "Regreso de orden de trabajo")
    assert StockLevel.objects.get(product=oil).average_cost == Decimal("21000.0000")
    for kind in (StockMovement.Kind.WORKSHOP_OUT, StockMovement.Kind.WORKSHOP_RETURN):
        with pytest.raises(ValidationError, match="debe ser positiva"):
            record_movement(kind=kind, product=oil, warehouse=warehouse, quantity=-1, user=clerk)


def test_a_part_cannot_leave_without_stock(clerk, oil, warehouse):
    from apps.inventory.services import InsufficientStock

    with pytest.raises(InsufficientStock):
        record_movement(kind=StockMovement.Kind.WORKSHOP_OUT, product=oil, warehouse=warehouse, quantity=11, user=clerk)


# --- admin de solo lectura ---------------------------------------------------------

def test_the_admin_only_shows(moto, clerk, oil, warehouse):
    order = receive(moto, clerk, mechanic=clerk)
    line(order, oil, clerk, approved=True, movement=take(oil, warehouse, clerk))
    WorkOrderApproval.objects.create(work_order=order, approved_by="Jorge Ramírez", channel="PHONE", total=Decimal("32000"), recorded_by=clerk)
    WorkOrderEvent.objects.create(work_order=order, status=Status.RECEIVED, user=clerk)
    client = Client()
    client.force_login(User.objects.create_superuser("jefe", password="clave-de-prueba-123"))
    listing = client.get("/admin/workshop/workorder/").content.decode()
    assert order.number in listing and "Recibida" in listing
    page = client.get(f"/admin/workshop/workorder/{order.pk}/change/")
    assert page.status_code == 200
    html = page.content.decode()
    assert "Jorge Ramírez" in html and "Por llamada" in html and "Aceite 20W50" in html
    assert 'name="_save"' not in html  # sin guardar
    assert client.get("/admin/workshop/workorder/add/").status_code == 403
    assert client.post(f"/admin/workshop/workorder/{order.pk}/delete/").status_code == 403
