"""Orden simplificada (spec 013, T3): en la versión sencilla no hay aprobación del cliente."""
import uuid
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.inventory.models import StockMovement
from apps.inventory.services import InsufficientStock
from apps.invoicing.models import Business
from apps.sales.services import create_sale

from . import work_orders as svc
from .models import WorkOrder
from .test_work_orders import clerk, events, labor, main, mechanic, moto, oil, order, pads, part, stock  # noqa: F401

pytestmark = pytest.mark.django_db
Status = WorkOrder.Status
D = Decimal


@pytest.fixture
def simple(db):
    business = Business.load()
    business.simple_mode = business.workshop_enabled = True
    business.save()
    return business


@pytest.fixture
def unassigned(moto, clerk, simple):
    """El taller pequeño recibe la moto sin asignar mecánico."""
    return svc.receive_order(user=clerk, motorcycle=moto, mileage=15400, request="Cambio de aceite")


def test_what_is_added_is_approved_and_the_part_leaves_at_once(unassigned, clerk, oil, labor):
    assert unassigned.mechanic is None
    line = svc.add_line(order=unassigned, user=clerk, product=oil, quantity=1)
    unassigned.refresh_from_db()
    assert (line.approved, line.movement.kind, line.movement.reference) == (True, StockMovement.Kind.WORKSHOP_OUT, f"Orden {unassigned.number}")
    assert stock(oil) == 9
    assert unassigned.status == Status.IN_REPAIR
    work = svc.add_line(order=unassigned, user=clerk, product=labor, quantity=1, unit_price=D("20000"))
    assert (work.approved, work.movement) == (True, None)
    assert [s for s, _, _ in events(unassigned)] == [Status.RECEIVED, Status.IN_REPAIR]  # sin "Esperando aprobación"


def test_ready_charged_and_delivered_without_approval(unassigned, clerk, oil, labor, shift):
    svc.add_line(order=unassigned, user=clerk, product=oil, quantity=1)
    svc.add_line(order=unassigned, user=clerk, product=labor, quantity=1, unit_price=D("20000"))
    svc.mark_ready(order=unassigned, user=clerk)
    sales_order = svc.send_to_till(order=unassigned, user=clerk)
    assert sales_order.total == D("52000.00")
    create_sale(user=clerk, shift=shift, order=sales_order, lines=None, client_uuid=uuid.uuid4(),
                payments=[{"method": "CASH", "amount": D("52000")}])
    order = svc.deliver(order=unassigned, user=clerk)
    assert order.status == Status.DELIVERED
    assert stock(oil) == 9  # la caja no lo sacó otra vez
    assert not order.approvals.exists()
    assert [s for s, _, _ in events(order)] == [Status.RECEIVED, Status.IN_REPAIR, Status.READY, Status.READY, Status.DELIVERED]


def test_without_stock_nothing_is_added(unassigned, clerk, main):
    empty = part("FIL-AIRE", "Filtro de aire", "15000", 0, main, clerk)
    with pytest.raises(InsufficientStock):
        svc.add_line(order=unassigned, user=clerk, product=empty, quantity=1)
    assert not unassigned.lines.exists()
    unassigned.refresh_from_db()
    assert unassigned.status == Status.RECEIVED


def test_removing_a_part_that_left_brings_it_back(unassigned, clerk, oil, labor):
    line = svc.add_line(order=unassigned, user=clerk, product=oil, quantity=2)
    assert stock(oil) == 8
    svc.remove_line(line=line, user=clerk)
    line.refresh_from_db()
    assert line.returned_movement.unit_cost == line.movement.unit_cost
    assert stock(oil) == 10
    assert line not in svc.charged_lines(unassigned)
    with pytest.raises(ValidationError, match="ya volvió"):
        svc.remove_line(line=line, user=clerk)
    work = svc.add_line(order=unassigned, user=clerk, product=labor, quantity=1, unit_price=D("20000"))
    svc.remove_line(line=work, user=clerk)  # la mano de obra simplemente se quita
    assert not unassigned.lines.filter(pk=work.pk).exists()


def test_the_labor_price_changes_until_the_order_is_ready(unassigned, clerk, oil, labor):
    work = svc.add_line(order=unassigned, user=clerk, product=labor, quantity=1)
    with pytest.raises(ValidationError, match="Ponle precio a Mano de obra"):
        svc.mark_ready(order=unassigned, user=clerk)
    svc.set_price(line=work, user=clerk, unit_price=D("25000"))
    svc.mark_ready(order=unassigned, user=clerk)
    with pytest.raises(ValidationError, match="está lista"):
        svc.set_price(line=work, user=clerk, unit_price=D("30000"))


def test_with_simple_mode_off_everything_waits_for_approval(order, clerk, mechanic, oil, labor):
    line = svc.add_line(order=order, user=clerk, product=oil, quantity=1)
    order.refresh_from_db()
    assert (line.approved, line.movement, order.status, stock(oil)) == (False, None, Status.RECEIVED, 10)
    work = svc.add_line(order=order, user=clerk, product=labor, quantity=1, unit_price=D("20000"))
    svc.send_for_approval(order=order, user=clerk)
    svc.approve(order=order, user=clerk, approved_by="Jorge", channel="PHONE")
    with pytest.raises(ValidationError, match="ya aprobó"):
        svc.set_price(line=work, user=clerk, unit_price=D("30000"))
    svc.take_part(line=line, user=clerk)
    with pytest.raises(ValidationError, match="regrésalo"):  # quitarlo no lo regresa: eso es aparte
        svc.remove_line(line=line, user=clerk)


def test_the_api_adds_approved_lines(unassigned, clerk, oil):
    client = APIClient()
    client.force_authenticate(clerk)
    res = client.post(f"/api/workshop/orders/{unassigned.pk}/lines/", {"product": oil.pk, "quantity": "1"}, format="json")
    assert res.status_code in (200, 201), res.data
    assert res.data["status"] == "IN_REPAIR"
    assert [(line["approved"], line["taken"]) for line in res.data["lines"]] == [(True, True)]
