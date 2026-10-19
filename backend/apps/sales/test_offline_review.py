"""Ventas sin conexión que quedan para revisión (spec 006, T8): producto desactivado y venta tardía
con fecha anterior a un conteo aprobado."""
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework.test import APIClient

from apps.inventory.counts import approve_count, open_count, record_line, submit_count, void_count
from apps.inventory.models import StockLevel, StockMovement, Warehouse
from apps.inventory.services import record_movement
from apps.sales import services
from apps.sales.models import Sale
from apps.sales.orders import create_order

pytestmark = pytest.mark.django_db
CASH = [{"method": "CASH", "amount": Decimal("10000000")}]


@pytest.fixture
def seller(make_user):
    return make_user("caja1", "Caja")


@pytest.fixture
def boss(make_user):
    return make_user("marta", "Jefe de bodega")


@pytest.fixture
def stocked(seller, warehouse, hammer, cable):
    for product, qty in ((hammer, 10), (cable, 300)):
        record_movement(kind=StockMovement.Kind.RECEIPT, product=product, warehouse=warehouse, quantity=qty, user=seller, unit_cost="1000")


def stock(product, warehouse):
    return StockLevel.objects.get(product=product, warehouse=warehouse).quantity


def sell(user, shift, product, *, offline=True, occurred_at=None):
    """Vende 1 al precio del catálogo, para que nada más la marque."""
    sale, _ = services.create_sale(
        user=user, shift=shift, client_uuid=uuid.uuid4(), payments=CASH, offline=offline, occurred_at=occurred_at,
        lines=[{"product": product, "quantity": 1, "unit_price": product.sale_price if offline else None}],
    )
    return sale


def deactivate(product):
    product.is_active = False
    product.save(update_fields=["is_active"])


# --- producto desactivado (decisión 6) ------------------------------------------

@pytest.mark.usefixtures("stocked")
def test_offline_sale_of_a_deactivated_product_is_accepted_for_review(seller, shift, warehouse, hammer):
    deactivate(hammer)
    sale = sell(seller, shift, hammer)  # mismo precio del catálogo y hay existencias: solo lo marca el producto
    assert sale.needs_review
    assert sale.total == Decimal("28000.00")
    assert stock(hammer, warehouse) == 9


@pytest.mark.usefixtures("stocked")
def test_online_sale_of_a_deactivated_product_is_rejected(seller, shift, warehouse, hammer):
    deactivate(hammer)
    with pytest.raises(ValidationError, match="MAR-16 está desactivado: ya no se vende."):
        sell(seller, shift, hammer, offline=False)
    assert not Sale.objects.exists()
    assert stock(hammer, warehouse) == 10


@pytest.mark.usefixtures("stocked")
def test_api_syncs_the_offline_sale_and_rejects_the_online_one(seller, shift, hammer):
    deactivate(hammer)
    client = APIClient()
    client.force_authenticate(seller)

    def body(**extra):
        return {
            "client_uuid": str(uuid.uuid4()), "shift": shift.pk, "payments": [{"method": "CASH", "amount": "50000"}],
            "lines": [{"product": hammer.pk, "quantity": "1", "unit_price": "28000"}], **extra,
        }

    res = client.post("/api/sales/", body(), format="json")
    assert res.status_code == 400
    assert "MAR-16 está desactivado" in str(res.data)
    res = client.post("/api/sales/", body(offline=True), format="json")
    assert res.status_code == 201, res.data
    assert res.data["needs_review"] is True


@pytest.mark.usefixtures("stocked")
def test_an_active_product_is_not_flagged(seller, shift, hammer):
    assert not sell(seller, shift, hammer).needs_review
    assert not sell(seller, shift, hammer, offline=False).needs_review


@pytest.mark.usefixtures("stocked")
def test_an_order_taken_before_deactivating_is_still_charged(make_user, seller, shift, hammer):
    order, _ = create_order(user=make_user("vende", "Ventas"), client_uuid=uuid.uuid4(), lines=[{"product": hammer, "quantity": 1}])
    deactivate(hammer)
    sale, _ = services.create_sale(user=seller, shift=shift, client_uuid=uuid.uuid4(), payments=CASH, order=order, lines=None)
    assert (sale.total, sale.needs_review) == (Decimal("28000.00"), False)  # el precio y el producto se acordaron en el pedido


# --- venta tardía frente a un conteo aprobado (decisión 3) ---------------------

def count(boss, warehouse, counted, approve=True):
    """Cuenta los productos dados ({producto: cantidad}) y, si se pide, aprueba. Devuelve el conteo."""
    physical, _ = open_count(user=boss, client_uuid=uuid.uuid4(), warehouse=warehouse)
    for product, quantity in counted.items():
        record_line(count=physical, line=physical.lines.get(product=product), user=boss, quantity=Decimal(quantity))
    submit_count(count=physical)
    if approve:
        physical = approve_count(count=physical, user=boss)
    return physical


@pytest.mark.usefixtures("stocked")
def test_a_late_sale_from_before_an_approved_count_is_flagged(seller, boss, shift, warehouse, hammer, cable):
    # El cajero vendió 1 martillo sin conexión a las 9; a las 10 se contaron 9 en el estante y se aprobó.
    physical = count(boss, warehouse, {hammer: 9})
    counted_at = physical.lines.get(product=hammer).counted_at
    assert stock(hammer, warehouse) == 9  # el ajuste ya descontó el martillo vendido

    sale = sell(seller, shift, hammer, occurred_at=counted_at - timedelta(hours=1))
    assert sale.needs_review  # llega ahora y lo vuelve a descontar: hay que revisarlo
    assert stock(hammer, warehouse) == 8

    assert not sell(seller, shift, hammer, occurred_at=counted_at + timedelta(minutes=1)).needs_review  # después del conteo: normal
    assert not sell(seller, shift, cable, occurred_at=counted_at - timedelta(hours=1)).needs_review  # el cable no se contó
    # Contado exactamente a esa hora también entra en lo esperado del conteo.
    assert sell(seller, shift, hammer, occurred_at=counted_at).needs_review


@pytest.mark.usefixtures("stocked")
def test_only_approved_counts_with_that_product_and_warehouse_matter(seller, boss, shift, warehouse, hammer, cable):
    before = timezone.now() - timedelta(hours=1)
    pending = count(boss, warehouse, {hammer: 10}, approve=False)  # enviado, sin aprobar: la venta sí entrará en lo esperado
    assert not sell(seller, shift, hammer, occurred_at=before).needs_review
    void_count(count=pending, user=boss, note="Mal contado")  # anulado: no ajustó nada
    assert not sell(seller, shift, hammer, occurred_at=before).needs_review

    other = Warehouse.objects.create(code="LOC", name="Local")
    record_movement(kind=StockMovement.Kind.RECEIPT, product=cable, warehouse=other, quantity=50, user=boss, unit_cost="1000")
    count(boss, other, {cable: 50})
    assert not sell(seller, shift, cable, occurred_at=before).needs_review  # se contó otra bodega


@pytest.mark.usefixtures("stocked")
def test_a_line_left_uncounted_does_not_flag_but_one_marked_zero_does(seller, boss, shift, warehouse, hammer, cable):
    before = timezone.now() - timedelta(hours=1)
    physical, _ = open_count(user=boss, client_uuid=uuid.uuid4(), warehouse=warehouse)
    record_line(count=physical, line=physical.lines.get(product=hammer), user=boss, quantity=Decimal(10))
    submit_count(count=physical)
    approve_count(count=physical, user=boss)  # el cable quedó sin contar: no se ajustó
    assert not sell(seller, shift, cable, occurred_at=before).needs_review

    physical, _ = open_count(user=boss, client_uuid=uuid.uuid4(), warehouse=warehouse)
    record_line(count=physical, line=physical.lines.get(product=hammer), user=boss, quantity=Decimal(10))
    submit_count(count=physical)
    approve_count(count=physical, user=boss, zero_uncounted="all")  # ahora el cable se marcó en 0
    assert sell(seller, shift, cable, occurred_at=before).needs_review
