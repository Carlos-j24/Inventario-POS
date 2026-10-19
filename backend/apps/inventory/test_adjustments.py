"""Ajustes de inventario (spec 006, T3)."""
import threading
import uuid
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import connection
from django.db.models import Sum
from rest_framework.test import APIClient

from apps.catalog.models import Category, Product, Unit
from apps.reports.costs import inventory_report

from .adjustments import approve_adjustment, create_adjustment
from .models import Adjustment, StockLevel, StockMovement
from .services import record_movement

pytestmark = pytest.mark.django_db
URL = "/api/inventory/adjustments/"


def api(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.fixture
def helper(make_user):
    return make_user("pedro", "Auxiliar de bodega")  # inventory.receive y count, sin adjust


@pytest.fixture
def boss(make_user):
    return make_user("marta", "Jefe de bodega")  # inventory.adjust


@pytest.fixture
def stocked(boss, warehouse, hammer, cable):
    record_movement(kind=StockMovement.Kind.RECEIPT, product=hammer, warehouse=warehouse, quantity=10, user=boss, unit_cost="20000")
    record_movement(kind=StockMovement.Kind.RECEIPT, product=cable, warehouse=warehouse, quantity=300, user=boss, unit_cost="1800")


def stock(product, warehouse):
    return StockLevel.objects.get(product=product, warehouse=warehouse).quantity


def body(warehouse, *lines, reason="DAMAGE", note="Se cayó del estante"):
    return {"client_uuid": str(uuid.uuid4()), "warehouse": warehouse.pk, "reason": reason, "note": note, "lines": list(lines)}


def line(product, quantity, direction="OUT", **extra):
    return {"product": product.pk, "quantity": str(quantity), "direction": direction, **extra}


# --- flujo ---------------------------------------------------------------------

@pytest.mark.usefixtures("stocked")
def test_helper_reports_damage_and_boss_approves(helper, boss, warehouse, hammer):
    before = Decimal(inventory_report()["totals"]["value"])
    res = api(helper).post(URL, body(warehouse, line(hammer, 3)), format="json")
    assert res.status_code == 201, res.data
    number = res.data["number"]  # en PostgreSQL los id no vuelven a 1 entre tests: no se asume
    assert number == f"AJ-{res.data['id']:06d}"
    assert (res.data["status"], res.data["requested_by"]) == ("PENDING", "pedro")
    assert stock(hammer, warehouse) == 10  # pendiente: no mueve nada
    assert api(helper).post(f"{URL}{res.data['id']}/approve/").status_code == 403

    res = api(boss).post(f"{URL}{res.data['id']}/approve/")
    assert (res.status_code, res.data["status"], res.data["decided_by"]) == (200, "APPROVED", "marta")
    assert stock(hammer, warehouse) == 7
    movement = Adjustment.objects.get().lines.get().movement
    assert (movement.kind, movement.quantity, movement.unit_cost, movement.reference) == (
        "ADJUSTMENT", Decimal("-3.000"), Decimal("20000.0000"), f"{number} Daño",
    )
    # Criterio de la spec: 3 martillos a $20.000 bajan el inventario valorizado en $60.000.
    assert before - Decimal(inventory_report()["totals"]["value"]) == Decimal("60000.00")


@pytest.mark.usefixtures("stocked")
def test_boss_can_approve_their_own(boss, warehouse, hammer):
    adjustment = api(boss).post(URL, body(warehouse, line(hammer, 1), reason="INTERNAL_USE", note="Para el mostrador"), format="json").data
    assert api(boss).post(f"{URL}{adjustment['id']}/approve/").data["status"] == "APPROVED"


@pytest.mark.usefixtures("stocked")
def test_an_out_line_cannot_leave_negative_stock_and_nothing_is_applied(boss, warehouse, hammer, cable):
    adjustment = api(boss).post(URL, body(warehouse, line(cable, 10), line(hammer, 11)), format="json").data
    res = api(boss).post(f"{URL}{adjustment['id']}/approve/")
    assert res.status_code == 400 and "Stock insuficiente" in str(res.data)
    assert (stock(cable, warehouse), stock(hammer, warehouse)) == (300, 10)  # ni la primera línea
    assert Adjustment.objects.get().status == "PENDING"
    assert not StockMovement.objects.filter(kind="ADJUSTMENT").exists()


@pytest.mark.usefixtures("stocked")
def test_quantities_in_a_presentation_are_stored_in_base_units(boss, warehouse, cable):
    adjustment = api(boss).post(URL, body(warehouse, line(cable, 1, unit="rollo")), format="json").data
    assert (adjustment["lines"][0]["quantity"], adjustment["lines"][0]["base_quantity"], adjustment["lines"][0]["unit"]) == ("1.000", "-100.000", "rollo")
    api(boss).post(f"{URL}{adjustment['id']}/approve/")
    assert stock(cable, warehouse) == 200


# --- reglas de motivo y líneas -------------------------------------------------

@pytest.mark.parametrize("payload, message", [
    ({"reason": "DAMAGE", "direction": "IN"}, "solo puede sacar"),
    ({"reason": "LOSS", "direction": "IN"}, "solo puede sacar"),
    ({"reason": "SURPLUS", "direction": "OUT"}, "solo puede entrar"),
    ({"reason": "PHYSICAL_COUNT", "direction": "OUT"}, "los genera el conteo"),
    ({"reason": "DAMAGE", "note": "   "}, "Escribe una nota"),
    ({"reason": "DAMAGE", "quantity": "0"}, "mayor que cero"),
    ({"reason": "DAMAGE", "quantity": "1.5"}, "no se vende fraccionado"),
    ({"reason": "DAMAGE", "unit_cost": "100"}, "no lleva costo"),
    ({"reason": "DAMAGE", "unit": "rollo"}, "no se maneja en la unidad"),
])
def test_invalid_adjustments(boss, warehouse, hammer, payload, message):
    payload = {"direction": "OUT", "quantity": "1", **payload}
    lines = [line(hammer, payload.pop("quantity"), payload.pop("direction"),
                  **{k: payload.pop(k) for k in ("unit_cost", "unit") if k in payload})]
    res = api(boss).post(URL, body(warehouse, *lines, **payload), format="json")
    assert res.status_code == 400
    assert message in str(res.data)
    assert not Adjustment.objects.exists()


def test_service_checks_what_the_api_already_filters(boss, warehouse, hammer):
    """El conteo (T5) llamará al servicio directamente, sin el serializer."""
    with pytest.raises(ValidationError, match=r"entra \(IN\) o sale"):
        create_adjustment(user=boss, client_uuid=uuid.uuid4(), warehouse=warehouse, reason="RECORD_ERROR", note="x",
                          lines=[{"product": hammer, "quantity": "1", "direction": "UP"}])
    with pytest.raises(ValidationError, match="Escribe una nota"):
        create_adjustment(user=boss, client_uuid=uuid.uuid4(), warehouse=warehouse, reason="DAMAGE", note="   ",
                          lines=[{"product": hammer, "quantity": "1", "direction": "OUT"}])
    with pytest.raises(ValidationError, match="no tiene líneas"):
        create_adjustment(user=boss, client_uuid=uuid.uuid4(), warehouse=warehouse, reason="DAMAGE", note="x", lines=[])


@pytest.mark.usefixtures("stocked")
def test_record_error_goes_both_ways(boss, warehouse, hammer, cable):
    adjustment = api(boss).post(URL, body(warehouse, line(hammer, 2, "IN"), line(cable, 5), reason="RECORD_ERROR", note="Se digitó mal la entrada"), format="json").data
    api(boss).post(f"{URL}{adjustment['id']}/approve/")
    assert (stock(hammer, warehouse), stock(cable, warehouse)) == (12, 295)


# --- sobrantes -----------------------------------------------------------------

@pytest.mark.usefixtures("stocked")
def test_surplus_enters_at_the_current_average(boss, warehouse, hammer):
    adjustment = api(boss).post(URL, body(warehouse, line(hammer, 2, "IN"), reason="SURPLUS", note="Apareció en bodega"), format="json").data
    api(boss).post(f"{URL}{adjustment['id']}/approve/")
    movement = StockMovement.objects.get(kind="ADJUSTMENT")
    assert (movement.quantity, movement.unit_cost) == (Decimal("2.000"), Decimal("20000.0000"))
    assert StockLevel.objects.get(product=hammer, warehouse=warehouse).average_cost == Decimal("20000.0000")


def test_surplus_of_a_product_without_cost_needs_its_cost(boss, warehouse):
    pliers = Product.objects.create(sku="ALI-8", name="Alicate 8", category=Category.objects.create(name="H"),
                                    base_unit=Unit.objects.get(code="und"), sale_price=Decimal("15000"))
    adjustment = api(boss).post(URL, body(warehouse, line(pliers, 4, "IN"), reason="SURPLUS", note="Sin factura"), format="json").data
    res = api(boss).post(f"{URL}{adjustment['id']}/approve/")
    assert res.status_code == 400 and "indica el costo" in str(res.data)
    # También si ya tiene existencia registrada pero sin costo (p. ej. una venta sin conexión la dejó en negativo).
    StockLevel.objects.create(product=pliers, warehouse=warehouse, quantity=0, average_cost=0)
    res = api(boss).post(f"{URL}{adjustment['id']}/approve/")
    assert res.status_code == 400 and "indica el costo" in str(res.data)
    adjustment = api(boss).post(URL, body(warehouse, line(pliers, 4, "IN", unit_cost="9000"), reason="SURPLUS", note="Con costo"), format="json").data
    assert api(boss).post(f"{URL}{adjustment['id']}/approve/").status_code == 200
    level = StockLevel.objects.get(product=pliers, warehouse=warehouse)
    assert (level.quantity, level.average_cost) == (Decimal("4.000"), Decimal("9000.0000"))


@pytest.mark.usefixtures("stocked")
def test_surplus_cost_given_per_presentation_is_stored_per_base_unit(boss, warehouse, cable):
    adjustment = create_adjustment(
        user=boss, client_uuid=uuid.uuid4(), warehouse=warehouse, reason="SURPLUS", note="Rollo sin registrar",
        lines=[{"product": cable, "unit": Unit.objects.get(code="rollo"), "quantity": "1", "direction": "IN", "unit_cost": "250000"}],
    )[0]
    assert adjustment.lines.get().unit_cost == Decimal("2500.0000")  # $250.000 el rollo de 100 m


# --- rechazo, una sola vez, idempotencia ---------------------------------------

@pytest.mark.usefixtures("stocked")
def test_reject_moves_nothing_and_closes_it(boss, warehouse, hammer):
    adjustment = api(boss).post(URL, body(warehouse, line(hammer, 3)), format="json").data
    res = api(boss).post(f"{URL}{adjustment['id']}/reject/", {"note": ""}, format="json")
    assert res.status_code == 400 and "por qué" in str(res.data)
    res = api(boss).post(f"{URL}{adjustment['id']}/reject/", {"note": "Sí estaba, en otro estante"}, format="json")
    assert (res.data["status"], res.data["rejection_note"], res.data["decided_by"]) == ("REJECTED", "Sí estaba, en otro estante", "marta")
    assert stock(hammer, warehouse) == 10
    res = api(boss).post(f"{URL}{adjustment['id']}/approve/")
    assert res.status_code == 400 and "ya está rechazado" in str(res.data)


@pytest.mark.usefixtures("stocked")
def test_an_approved_adjustment_is_never_applied_twice(boss, warehouse, hammer):
    adjustment = api(boss).post(URL, body(warehouse, line(hammer, 3)), format="json").data
    api(boss).post(f"{URL}{adjustment['id']}/approve/")
    for action in ("approve", "reject"):
        res = api(boss).post(f"{URL}{adjustment['id']}/{action}/", {"note": "x"}, format="json")
        assert res.status_code == 400 and "ya está aprobado" in str(res.data)
    assert stock(hammer, warehouse) == 7


@pytest.mark.usefixtures("stocked")
def test_same_client_uuid_creates_one_adjustment(helper, warehouse, hammer):
    payload = body(warehouse, line(hammer, 1))
    first, second = api(helper).post(URL, payload, format="json"), api(helper).post(URL, payload, format="json")
    assert (first.status_code, second.status_code, first.data["id"]) == (201, 200, second.data["id"])
    assert Adjustment.objects.count() == 1


# --- listado, valor y permisos -------------------------------------------------

@pytest.mark.usefixtures("stocked")
def test_list_filter_and_value_only_with_costs_permission(boss, make_user, warehouse, hammer):
    first = api(boss).post(URL, body(warehouse, line(hammer, 3)), format="json").data
    second = api(boss).post(URL, body(warehouse, line(hammer, 1)), format="json").data
    api(boss).post(f"{URL}{first['id']}/approve/")
    assert [a["number"] for a in api(boss).get(URL).data] == [second["number"], first["number"]]  # recientes primero
    assert [a["number"] for a in api(boss).get(URL, {"status": "PENDING"}).data] == [second["number"]]
    assert api(boss).get(f"{URL}{first['id']}/").data["lines"][0]["value"] is None  # sin reports.costs

    owner = make_user("dueno", "Administrador")
    rows = {a["number"]: a for a in api(owner).get(URL).data}
    assert rows[first["number"]]["lines"][0]["value"] == "-60000.00"  # aprobado: costo del movimiento
    assert rows[second["number"]]["lines"][0]["value"] == "-20000.00"  # pendiente: promedio vigente


def test_permissions(make_user, warehouse, hammer):
    seller = make_user("vende", "Ventas")
    assert api(seller).get(URL).status_code == 403
    assert api(seller).post(URL, body(warehouse, line(hammer, 1)), format="json").status_code == 403
    assert APIClient().get(URL).status_code == 403


@pytest.mark.usefixtures("stocked")
def test_kardex_still_matches_stock(boss, warehouse, hammer, cable):
    for lines in ([line(hammer, 2)], [line(cable, 30)], [line(hammer, 1, "IN")]):
        reason = "SURPLUS" if lines[0]["direction"] == "IN" else "LOSS"
        adjustment = api(boss).post(URL, body(warehouse, *lines, reason=reason), format="json").data
        api(boss).post(f"{URL}{adjustment['id']}/approve/")
    for product in (hammer, cable):
        total = StockMovement.objects.filter(product=product, warehouse=warehouse).aggregate(q=Sum("quantity"))["q"]
        assert total == stock(product, warehouse)


# --- concurrencia (PostgreSQL) ---------------------------------------------------

@pytest.mark.skipif(connection.vendor == "sqlite", reason="SQLite no permite escrituras concurrentes")
@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_two_approvals_at_once_apply_it_once(boss, warehouse, hammer, stocked):  # pragma: no cover
    adjustment, _ = create_adjustment(user=boss, client_uuid=uuid.uuid4(), warehouse=warehouse, reason="DAMAGE",
                                      note="x", lines=[{"product": hammer, "quantity": "3", "direction": "OUT"}])
    errors = []

    def approve():
        try:
            approve_adjustment(adjustment=adjustment, user=boss)
        except ValidationError as exc:
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=approve) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(errors) == 1
    assert stock(hammer, warehouse) == 7
    assert StockMovement.objects.filter(kind="ADJUSTMENT").count() == 1
