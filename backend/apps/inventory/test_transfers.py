"""Traslados entre bodegas (spec 006, T7)."""
import uuid
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db.models import Sum
from rest_framework.test import APIClient

from apps.accounts.models import Permission, Role
from apps.reports.costs import inventory_report

from .models import StockLevel, StockMovement, Transfer, Warehouse
from .services import record_movement
from .transfers import create_transfer

pytestmark = pytest.mark.django_db
URL = "/api/inventory/transfers/"


def api(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.fixture
def helper(make_user):
    return make_user("pedro", "Auxiliar de bodega")


@pytest.fixture
def shop(db):
    return Warehouse.objects.create(code="LOC", name="Local")


@pytest.fixture
def stocked(helper, warehouse, hammer, cable):
    record_movement(kind=StockMovement.Kind.RECEIPT, product=hammer, warehouse=warehouse, quantity=10, user=helper, unit_cost="20000")
    record_movement(kind=StockMovement.Kind.RECEIPT, product=cable, warehouse=warehouse, quantity=300, user=helper, unit_cost="1800")


def stock(product, warehouse):
    level = StockLevel.objects.filter(product=product, warehouse=warehouse).first()
    return level.quantity if level else Decimal(0)


def body(origin, destination, *lines, note=""):
    return {"client_uuid": str(uuid.uuid4()), "origin": origin.pk, "destination": destination.pk, "note": note, "lines": list(lines)}


def line(product, quantity, **extra):
    return {"product": product.pk, "quantity": str(quantity), **extra}


# --- flujo ---------------------------------------------------------------------

@pytest.mark.usefixtures("stocked")
def test_helper_moves_goods_in_one_step(helper, warehouse, shop, hammer):
    before = Decimal(inventory_report()["totals"]["value"])
    res = api(helper).post(URL, body(warehouse, shop, line(hammer, 5), note="Para la vitrina"), format="json")
    assert res.status_code == 201, res.data
    number = res.data["number"]  # en PostgreSQL los id no vuelven a 1 entre tests: no se asume
    assert number == f"TR-{res.data['id']:06d}"
    assert (res.data["origin"], res.data["destination"], res.data["created_by"], res.data["note"]) == ("PRAL", "LOC", "pedro", "Para la vitrina")
    # Criterio de la spec: −5 en el origen y +5 en el destino con el mismo costo unitario.
    assert (stock(hammer, warehouse), stock(hammer, shop)) == (5, 5)
    out = StockMovement.objects.get(kind="TRANSFER_OUT")
    inbound = StockMovement.objects.get(kind="TRANSFER_IN")
    assert (out.warehouse, out.quantity, out.unit_cost) == (warehouse, Decimal("-5.000"), Decimal("20000.0000"))
    assert (inbound.warehouse, inbound.quantity, inbound.unit_cost) == (shop, Decimal("5.000"), Decimal("20000.0000"))
    assert out.reference == inbound.reference == f"{number} PRAL a LOC"
    assert StockLevel.objects.get(product=hammer, warehouse=shop).average_cost == Decimal("20000.0000")
    transfer_line = Transfer.objects.get().lines.get()
    assert (transfer_line.out_movement, transfer_line.in_movement) == (out, inbound)
    # ... y el inventario valorizado total no cambia.
    assert Decimal(inventory_report()["totals"]["value"]) == before


@pytest.mark.usefixtures("stocked")
def test_entering_at_the_origin_cost_keeps_the_total_value_with_stock_at_another_cost(helper, warehouse, shop, hammer):
    record_movement(kind=StockMovement.Kind.RECEIPT, product=hammer, warehouse=shop, quantity=2, user=helper, unit_cost="26000")
    before = Decimal(inventory_report()["totals"]["value"])
    api(helper).post(URL, body(warehouse, shop, line(hammer, 4)), format="json")
    # En el local: 2 a 26.000 y 4 a 20.000 → promedio 22.000.
    assert StockLevel.objects.get(product=hammer, warehouse=shop).average_cost == Decimal("22000.0000")
    assert Decimal(inventory_report()["totals"]["value"]) == before


@pytest.mark.usefixtures("stocked")
def test_quantities_in_a_presentation_are_stored_in_base_units(helper, warehouse, shop, cable):
    res = api(helper).post(URL, body(warehouse, shop, line(cable, 2, unit="rollo")), format="json")
    assert (res.data["lines"][0]["quantity"], res.data["lines"][0]["base_quantity"], res.data["lines"][0]["unit"]) == ("2.000", "200.000", "rollo")
    assert (stock(cable, warehouse), stock(cable, shop)) == (100, 200)
    assert StockLevel.objects.get(product=cable, warehouse=shop).average_cost == Decimal("1800.0000")  # por metro, no por rollo


@pytest.mark.usefixtures("stocked")
def test_cannot_leave_the_origin_negative_and_nothing_is_applied(helper, warehouse, shop, hammer, cable):
    res = api(helper).post(URL, body(warehouse, shop, line(cable, 50), line(hammer, 11)), format="json")
    assert res.status_code == 400
    assert "Stock insuficiente de MAR-16 en PRAL" in str(res.data)
    assert not Transfer.objects.exists()
    assert not StockMovement.objects.filter(kind__in=["TRANSFER_OUT", "TRANSFER_IN"]).exists()
    assert (stock(cable, warehouse), stock(cable, shop)) == (300, 0)  # la línea que sí alcanzaba tampoco entró


# --- reglas --------------------------------------------------------------------

@pytest.mark.parametrize("payload, message", [
    ({"same": True}, "bodegas distintas"),
    ({"quantity": "0"}, "mayor que cero"),
    ({"quantity": "1.5"}, "no se vende fraccionado"),
    ({"unit": "rollo"}, "no se maneja en la unidad"),
    ({"lines": []}, "lines"),
])
@pytest.mark.usefixtures("stocked")
def test_invalid_transfers(helper, warehouse, shop, hammer, payload, message):
    lines = payload.get("lines", [line(hammer, payload.get("quantity", "1"), **({"unit": payload["unit"]} if "unit" in payload else {}))])
    res = api(helper).post(URL, {**body(warehouse, warehouse if payload.get("same") else shop), "lines": lines}, format="json")
    assert res.status_code == 400
    assert message in str(res.data)
    assert not Transfer.objects.exists()


@pytest.mark.usefixtures("stocked")
def test_inactive_warehouses_neither_send_nor_receive(helper, warehouse, shop, hammer):
    shop.is_active = False
    shop.save()
    res = api(helper).post(URL, body(warehouse, shop, line(hammer, 1)), format="json")
    assert (res.status_code, "La bodega LOC está inactiva." in str(res.data)) == (400, True)
    res = api(helper).post(URL, body(shop, warehouse, line(hammer, 1)), format="json")
    assert (res.status_code, "La bodega LOC está inactiva." in str(res.data)) == (400, True)
    assert not Transfer.objects.exists()


def test_service_checks_lines(helper, warehouse, shop):
    with pytest.raises(ValidationError, match="no tiene líneas"):
        create_transfer(user=helper, client_uuid=uuid.uuid4(), origin=warehouse, destination=shop, lines=[])


@pytest.mark.usefixtures("stocked")
def test_same_client_uuid_creates_one_transfer(helper, warehouse, shop, hammer):
    payload = body(warehouse, shop, line(hammer, 2))
    first = api(helper).post(URL, payload, format="json")
    again = api(helper).post(URL, payload, format="json")
    assert (first.status_code, again.status_code) == (201, 200)
    assert again.data["id"] == first.data["id"]
    assert (Transfer.objects.count(), stock(hammer, shop)) == (1, 2)
    # Un reintento devuelve el que ya quedó aunque ahora no se pudiera hacer de nuevo.
    shop.is_active = False
    shop.save()
    assert api(helper).post(URL, payload, format="json").status_code == 200


# --- consulta y permisos -------------------------------------------------------

@pytest.mark.usefixtures("stocked")
def test_list_detail_filter_and_value_only_with_costs_permission(helper, make_user, warehouse, shop, hammer):
    other = Warehouse.objects.create(code="BOD2", name="Bodega 2")
    first = api(helper).post(URL, body(warehouse, shop, line(hammer, 3)), format="json").data
    second = api(helper).post(URL, body(warehouse, other, line(hammer, 1)), format="json").data
    assert [t["number"] for t in api(helper).get(URL).data] == [second["number"], first["number"]]  # recientes primero
    assert [t["number"] for t in api(helper).get(URL, {"warehouse": shop.pk}).data] == [first["number"]]  # entra al local
    assert len(api(helper).get(URL, {"warehouse": warehouse.pk}).data) == 2  # salen de la principal
    assert api(helper).get(f"{URL}{first['id']}/").data["lines"][0]["value"] is None  # sin reports.costs

    owner = make_user("dueno", "Administrador")
    assert api(owner).get(f"{URL}{first['id']}/").data["lines"][0]["value"] == "60000.00"


def test_permissions(make_user, warehouse, shop, hammer):
    assert set(Role.objects.filter(permissions__code="inventory.transfer").values_list("name", flat=True)) == {
        "Administrador", "Jefe de bodega", "Auxiliar de bodega",
    }
    assert Permission.objects.get(code="inventory.transfer").description == "Trasladar mercancía entre bodegas"
    for user in (make_user("vende", "Ventas"), make_user("super", "Supervisor"), make_user("caja", "Caja")):
        assert api(user).get(URL).status_code == 403
        assert api(user).post(URL, body(warehouse, shop, line(hammer, 1)), format="json").status_code == 403
    assert api(make_user("marta", "Jefe de bodega")).get(URL).status_code == 200
    assert APIClient().get(URL).status_code == 403


@pytest.mark.usefixtures("stocked")
def test_kardex_still_matches_stock(helper, warehouse, shop, hammer, cable):
    api(helper).post(URL, body(warehouse, shop, line(hammer, 4), line(cable, 1, unit="rollo")), format="json")
    api(helper).post(URL, body(shop, warehouse, line(hammer, 1)), format="json")  # un error se corrige al revés
    for product in (hammer, cable):
        for place in (warehouse, shop):
            total = StockMovement.objects.filter(product=product, warehouse=place).aggregate(q=Sum("quantity"))["q"]
            assert total == stock(product, place)
    assert (stock(hammer, warehouse), stock(hammer, shop)) == (7, 3)
