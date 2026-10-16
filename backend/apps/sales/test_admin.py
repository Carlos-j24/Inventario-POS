"""Spec 002, T7: en el admin se ve quién vendió y quién cobró, y los pedidos."""
import datetime
import uuid
from decimal import Decimal

import pytest
from django.test import Client

from apps.accounts.models import User
from apps.inventory.models import StockMovement
from apps.inventory.services import record_movement
from apps.sales.models import Order, business_date
from apps.sales.orders import create_order
from apps.sales.services import create_sale

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client():
    client = Client()
    client.force_login(User.objects.create_superuser("jefe", password="clave-de-prueba-123"))
    return client


@pytest.fixture
def paid_order(make_user, shift, warehouse, hammer):
    vendor, cashier = make_user("andres", "Ventas"), make_user("laura", "Caja")
    record_movement(kind=StockMovement.Kind.RECEIPT, product=hammer, warehouse=warehouse, quantity=5, user=cashier)
    order, _ = create_order(user=vendor, client_uuid=uuid.uuid4(), lines=[{"product": hammer, "quantity": 1}])
    sale, _ = create_sale(
        user=cashier, shift=shift, order=order, lines=None, client_uuid=uuid.uuid4(),
        payments=[{"method": "CASH", "amount": Decimal("28000")}],
    )
    return order, sale


def test_sales_list_shows_who_sold_who_charged_and_the_order(admin_client, paid_order):
    order, sale = paid_order
    html = admin_client.get("/admin/sales/sale/").content.decode()
    assert "vendió" in html and "cobró (cajero)" in html
    assert "andres" in html and "laura" in html
    assert str(order.code) in html


def test_sales_can_be_filtered_by_salesperson(admin_client, paid_order):
    _, sale = paid_order
    res = admin_client.get(f"/admin/sales/sale/?salesperson__id__exact={sale.salesperson_id}")
    assert res.status_code == 200
    assert sale.number in res.content.decode()


def test_orders_admin_lists_them_read_only_and_shows_expired(admin_client, make_user, hammer):
    vendor = make_user("andres", "Ventas")
    old, _ = create_order(user=vendor, client_uuid=uuid.uuid4(), lines=[{"product": hammer, "quantity": 1}])
    Order.objects.filter(pk=old.pk).update(business_date=business_date() - datetime.timedelta(days=1))

    html = admin_client.get("/admin/sales/order/").content.decode()
    assert str(old.code) in html
    # La celda de la fila, no el filtro lateral (que también dice "Vencido"): pendiente de ayer = vencido.
    assert '<td class="field-shown_status">Vencido</td>' in html
    assert admin_client.get(f"/admin/sales/order/{old.pk}/change/").status_code == 200
    assert admin_client.get("/admin/sales/order/add/").status_code == 403
