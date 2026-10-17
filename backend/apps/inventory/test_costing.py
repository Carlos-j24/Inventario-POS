"""Spec 004, T1: costo promedio ponderado y costo de lo vendido."""
import uuid
from decimal import Decimal

import pytest

from apps.accounts.models import Permission, Role
from apps.catalog.models import Unit
from apps.inventory.costing import next_average, replay_costs
from apps.inventory.models import StockLevel, StockMovement
from apps.inventory.services import record_movement
from apps.sales.returns import create_return, void_sale
from apps.sales.services import create_sale

D = Decimal
Kind = StockMovement.Kind


# --- la fórmula -----------------------------------------------------------------

@pytest.mark.parametrize("qty, avg, qty_in, cost, expected", [
    (10, 1000, 10, 2000, "1500.0000"),      # el ejemplo de la spec
    (0, 0, 5, 1234.5, "1234.5000"),         # sin existencias: el costo de la entrada
    (-2, 1500, 10, 3000, "3000.0000"),      # en negativo (ventas sin conexión): ídem
    (3, 1000, 1, 1001, "1000.2500"),        # cuatro decimales
])
def test_next_average(qty, avg, qty_in, cost, expected):
    assert next_average(qty, avg, qty_in, cost) == D(expected)


# --- en el kardex -------------------------------------------------------------------

pytestmark = pytest.mark.django_db


def level(product, warehouse):
    return StockLevel.objects.get(product=product, warehouse=warehouse)


def receive(product, warehouse, user, qty, cost, unit=None):
    return record_movement(kind=Kind.RECEIPT, product=product, warehouse=warehouse, quantity=qty,
                           unit_cost=D(cost), unit=unit, user=user)[0]


def test_receipts_average_and_sales_take_the_current_average(make_user, warehouse, hammer):
    user = make_user()
    receive(hammer, warehouse, user, 10, 1000)
    receive(hammer, warehouse, user, 10, 2000)
    assert level(hammer, warehouse).average_cost == D("1500")
    sale, _ = record_movement(kind=Kind.SALE, product=hammer, warehouse=warehouse, quantity=5, user=user)
    assert sale.unit_cost == D("1500")  # 5 × 1.500 = 7.500 de costo, como pide la spec
    assert level(hammer, warehouse).average_cost == D("1500")  # vender no cambia el promedio


def test_sale_cost_does_not_change_when_later_receipts_change_the_average(make_user, warehouse, hammer):
    user = make_user()
    receive(hammer, warehouse, user, 10, 1000)
    sale, _ = record_movement(kind=Kind.SALE, product=hammer, warehouse=warehouse, quantity=4, user=user)
    receive(hammer, warehouse, user, 6, 4000)  # (6 × 1.000 + 6 × 4.000) / 12 = 2.500
    assert level(hammer, warehouse).average_cost == D("2500")
    sale.refresh_from_db()
    assert sale.unit_cost == D("1000")


def test_presentation_cost_is_stored_per_base_unit(make_user, warehouse, cable):
    mov = receive(cable, warehouse, make_user(), 3, 100000, unit=Unit.objects.get(code="rollo"))
    assert mov.unit_cost == D("1000")  # 100.000 por rollo de 100 m
    assert level(cable, warehouse).average_cost == D("1000")


def test_presentation_cost_keeps_cents_per_base_unit(make_user, warehouse, cable):
    mov = receive(cable, warehouse, make_user(), 1, 99999, unit=Unit.objects.get(code="rollo"))
    assert mov.unit_cost == D("999.99")  # no se redondea a pesos enteros


def test_positive_adjustment_without_cost_keeps_the_average(make_user, warehouse, hammer):
    user = make_user()
    receive(hammer, warehouse, user, 10, 1000)
    adj, _ = record_movement(kind=Kind.ADJUSTMENT, product=hammer, warehouse=warehouse, quantity=2, user=user)
    assert adj.unit_cost == D("1000")
    assert level(hammer, warehouse).average_cost == D("1000")


# --- ventas, devoluciones y anulaciones ------------------------------------------------

@pytest.fixture
def cashier(make_user):
    return make_user("laura", "Caja")


def sell(cashier, shift, product, qty):
    sale, _ = create_sale(
        user=cashier, shift=shift, client_uuid=uuid.uuid4(), lines=[{"product": product, "quantity": qty}],
        payments=[{"method": "CASH", "amount": D("10000000")}],
    )
    return sale


def test_sale_line_movement_carries_cost(cashier, shift, warehouse, hammer):
    receive(hammer, warehouse, cashier, 10, 1000)
    receive(hammer, warehouse, cashier, 10, 2000)
    sale = sell(cashier, shift, hammer, 5)
    assert sale.lines.get().movement.unit_cost == D("1500")


def test_return_comes_back_at_the_cost_it_left_with(make_user, cashier, shift, warehouse, hammer):
    receive(hammer, warehouse, cashier, 10, 1000)
    sale = sell(cashier, shift, hammer, 4)  # salen a 1.000; quedan 6
    receive(hammer, warehouse, cashier, 6, 3000)  # promedio (6 × 1.000 + 6 × 3.000) / 12 = 2.000
    ret, _ = create_return(
        sale=sale, user=make_user("sofia", "Supervisor"), shift=shift, refund_method="CASH", reason="x",
        client_uuid=uuid.uuid4(), lines=[{"sale_line": sale.lines.get(), "quantity": 4}],
    )
    assert ret.lines.get().movement.unit_cost == D("1000")
    # (12 × 2.000 + 4 × 1.000) / 16 = 1.750: vuelve lo que salió barato, el promedio baja.
    assert level(hammer, warehouse).average_cost == D("1750")


def test_void_returns_stock_at_the_original_cost(make_user, cashier, shift, warehouse, hammer):
    receive(hammer, warehouse, cashier, 10, 1000)
    sale = sell(cashier, shift, hammer, 2)
    receive(hammer, warehouse, cashier, 8, 3000)  # (8 × 1.000 + 8 × 3.000) / 16 = 2.000
    void_sale(sale=sale, user=make_user("sofia", "Supervisor"), reason="Error")
    back = StockMovement.objects.get(kind=Kind.RETURN, reference=f"Anulación {sale.number}")
    assert back.unit_cost == D("1000")
    assert level(hammer, warehouse).average_cost == D("1888.8889")  # (16 × 2.000 + 2 × 1.000) / 18


# --- recálculo de datos anteriores (migración) ----------------------------------------------

def test_replay_assigns_estimated_costs_to_old_sales(cashier, shift, warehouse, hammer, cable):
    receive(hammer, warehouse, cashier, 10, 1000)
    receive(hammer, warehouse, cashier, 10, 2000)
    old_sale = sell(cashier, shift, hammer, 5)
    receive(cable, warehouse, cashier, 100, 900)
    # Simula una base anterior a la spec 004: las salidas sin costo y sin promedio guardado.
    StockMovement.objects.filter(quantity__lt=0).update(unit_cost=None)
    StockLevel.objects.update(average_cost=0)

    replay_costs(StockMovement, StockLevel)

    mov = old_sale.lines.get().movement
    mov.refresh_from_db()
    assert (mov.unit_cost, mov.cost_estimated) == (D("1500"), True)
    assert level(hammer, warehouse).average_cost == D("1500")
    assert level(cable, warehouse).average_cost == D("900")
    assert not StockMovement.objects.filter(kind=Kind.RECEIPT, cost_estimated=True).exists()


# --- permiso -----------------------------------------------------------------------------

def test_reports_costs_permission_is_only_for_administrators(make_user):
    assert Permission.objects.filter(code="reports.costs").exists()
    assert make_user("admin", "Administrador").has_app_permission("reports.costs")
    for role in ("Supervisor", "Jefe de bodega", "Caja"):
        assert not make_user(role, role).has_app_permission("reports.costs"), role
    assert Role.objects.get(name="Supervisor").permissions.filter(code="reports.view").exists()
