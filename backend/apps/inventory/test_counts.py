"""Conteos físicos (spec 006, T5)."""
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.db.models import Sum
from rest_framework.test import APIClient

from apps.catalog.models import Category, Product, Unit

from .models import Adjustment, CountLine, PhysicalCount, StockLevel, StockMovement
from .services import record_movement

pytestmark = pytest.mark.django_db
URL = "/api/inventory/counts/"


def api(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.fixture
def helper(make_user):
    return make_user("pedro", "Auxiliar de bodega")  # inventory.count, sin adjust


@pytest.fixture
def boss(make_user):
    return make_user("marta", "Jefe de bodega")  # inventory.adjust


def receive(product, warehouse, user, qty, cost="1000"):
    record_movement(kind=StockMovement.Kind.RECEIPT, product=product, warehouse=warehouse, quantity=qty, user=user, unit_cost=cost)


@pytest.fixture
def stocked(boss, warehouse, hammer, cable):
    receive(hammer, warehouse, boss, 10, "20000")
    receive(cable, warehouse, boss, 10, "1800")


def stock(product, warehouse):
    return StockLevel.objects.get(product=product, warehouse=warehouse).quantity


def open_count(user, warehouse, **extra):
    res = api(user).post(URL, {"client_uuid": str(uuid.uuid4()), "warehouse": warehouse.pk, **extra}, format="json")
    assert res.status_code == 201, res.data
    return res.data


def line_of(count, sku):
    return next(line for line in count["lines"] if line["sku"] == sku)


def count_line(user, count, sku, quantity, unit=None):
    body = {"quantity": str(quantity), **({"unit": unit} if unit else {})}
    return api(user).patch(f"{URL}{count['id']}/lines/{line_of(count, sku)['id']}/", body, format="json")


def sell(product, warehouse, user, qty, when):
    record_movement(kind=StockMovement.Kind.SALE, product=product, warehouse=warehouse, quantity=qty, user=user,
                    occurred_at=when, allow_negative=True)


# --- abrir ---------------------------------------------------------------------

@pytest.mark.usefixtures("stocked")
def test_open_lists_active_products_and_inactive_ones_with_stock(helper, boss, warehouse, hammer, cable):
    old = Product.objects.create(sku="VIEJO", name="Descontinuado con stock", category=hammer.category, base_unit=Unit.objects.get(code="und"), sale_price=1)
    gone = Product.objects.create(sku="NADA", name="Descontinuado sin stock", category=hammer.category, base_unit=Unit.objects.get(code="und"), sale_price=1, is_active=False)
    receive(old, warehouse, boss, 2)
    emptied = Product.objects.create(sku="AGOTADO", name="Descontinuado ya vendido", category=hammer.category, base_unit=Unit.objects.get(code="und"), sale_price=1)
    receive(emptied, warehouse, boss, 1)
    sell(emptied, warehouse, boss, 1, None)  # su existencia quedó en 0
    Product.objects.filter(pk__in=[old.pk, emptied.pk]).update(is_active=False)
    count = open_count(helper, warehouse)
    assert count["number"] == f"CF-{count['id']:06d}"
    assert (count["status"], count["opened_by"], count["total"], count["counted"]) == ("OPEN", "pedro", 3, 0)
    assert sorted(line["sku"] for line in count["lines"]) == ["CAB-12", "MAR-16", "VIEJO"]
    assert gone.sku not in [line["sku"] for line in count["lines"]]


@pytest.mark.usefixtures("stocked")
def test_by_category_and_no_overlapping_open_counts(helper, boss, warehouse, hammer, cable):
    tools = open_count(helper, warehouse, category=hammer.category_id)
    assert [line["sku"] for line in tools["lines"]] == ["MAR-16"]
    electric = open_count(helper, warehouse, category=cable.category_id)  # no se cruzan
    res = api(helper).post(URL, {"client_uuid": str(uuid.uuid4()), "warehouse": warehouse.pk}, format="json")
    assert res.status_code == 400
    assert tools["number"] in str(res.data) and electric["number"] in str(res.data)
    count_line(helper, tools, "MAR-16", 10)
    api(helper).post(f"{URL}{tools['id']}/submit/")  # enviado sin aprobar: sigue bloqueando
    res = api(helper).post(URL, {"client_uuid": str(uuid.uuid4()), "warehouse": warehouse.pk, "category": hammer.category_id}, format="json")
    assert res.status_code == 400 and tools["number"] in str(res.data)
    api(boss).post(f"{URL}{tools['id']}/void/", {"note": "Se abrió por error"}, format="json")
    api(boss).post(f"{URL}{electric['id']}/void/", {"note": "Se abrió por error"}, format="json")
    open_count(helper, warehouse)  # ya no hay conteos abiertos


@pytest.mark.usefixtures("stocked")
def test_same_client_uuid_opens_one_count(helper, warehouse):
    payload = {"client_uuid": str(uuid.uuid4()), "warehouse": warehouse.pk}
    first, second = api(helper).post(URL, payload, format="json"), api(helper).post(URL, payload, format="json")
    assert (first.status_code, second.status_code, first.data["id"]) == (201, 200, second.data["id"])
    assert PhysicalCount.objects.count() == 1


def test_nothing_to_count(helper, warehouse):
    res = api(helper).post(URL, {"client_uuid": str(uuid.uuid4()), "warehouse": warehouse.pk, "category": Category.objects.create(name="Vacía").pk}, format="json")
    assert res.status_code == 400 and "No hay productos" in str(res.data)


# --- contar a ciegas -----------------------------------------------------------

@pytest.mark.usefixtures("stocked")
def test_blind_count_and_presentation_units(helper, boss, warehouse):
    count = open_count(helper, warehouse)
    res = count_line(helper, count, "CAB-12", 1, unit="rollo")  # 1 rollo = 100 m
    assert (res.status_code, res.data["counted"], res.data["counted_by"]) == (200, "100.000", "pedro")
    assert (res.data["expected"], res.data["difference"], res.data["value"]) == (None, None, None)  # ciego
    assert res.data["units"] == [{"unit": "rollo", "factor": "100.000", "barcode": None}]
    cable_unit = CountLine.objects.get(pk=res.data["id"]).product.units.get()
    cable_unit.is_active = False
    cable_unit.save()
    assert line_of(api(helper).get(f"{URL}{count['id']}/").data, "CAB-12")["units"] == []  # desactivada: no se ofrece
    detail = api(boss).get(f"{URL}{count['id']}/").data  # quien aprueba sí ve lo esperado
    assert (line_of(detail, "CAB-12")["expected"], line_of(detail, "CAB-12")["difference"]) == ("10.000", "90.000")
    assert (line_of(detail, "MAR-16")["expected"], detail["counted"]) == (None, 1)  # sin contar
    assert count_line(helper, count, "CAB-12", -1).status_code == 400
    assert count_line(helper, count, "MAR-16", "1.5").status_code == 400  # no se fracciona


# --- el criterio de la spec y la caja que sigue vendiendo --------------------

@pytest.mark.usefixtures("stocked")
def test_sales_after_the_count_line_are_not_counted_twice(helper, boss, warehouse, cable):
    """Hay 10 m de cable, se cuentan 8 y después se venden 2: el ajuste es −2 (no −4) y quedan 6."""
    count = open_count(helper, warehouse, category=cable.category_id)
    counted_at = CountLine.objects.get(pk=line_of(count, "CAB-12")["id"])
    count_line(helper, count, "CAB-12", 8)
    counted_at.refresh_from_db()
    sell(cable, warehouse, boss, 2, counted_at.counted_at + timedelta(seconds=1))
    api(helper).post(f"{URL}{count['id']}/submit/")
    res = api(boss).post(f"{URL}{count['id']}/approve/", {}, format="json")
    assert (res.status_code, res.data["status"], res.data["decided_by"]) == (200, "APPROVED", "marta")
    line = line_of(res.data, "CAB-12")
    assert (line["expected"], line["difference"]) == ("10.000", "-2.000")
    assert stock(cable, warehouse) == 6
    adjustment = Adjustment.objects.get()
    assert (res.data["adjustment"], adjustment.reason, adjustment.status, adjustment.note) == (
        adjustment.number, "PHYSICAL_COUNT", "APPROVED", f"Conteo físico {count['number']}",
    )
    assert adjustment.lines.get().base_quantity == Decimal("-2.000")


@pytest.mark.usefixtures("stocked")
def test_an_offline_sale_made_before_the_count_that_arrives_later_is_counted(helper, boss, warehouse, cable):
    count = open_count(helper, warehouse, category=cable.category_id)
    count_line(helper, count, "CAB-12", 8)
    line = CountLine.objects.get(pk=line_of(count, "CAB-12")["id"])
    sell(cable, warehouse, boss, 2, line.counted_at - timedelta(minutes=5))  # se vendió antes de contar, llegó después
    api(helper).post(f"{URL}{count['id']}/submit/")
    res = api(boss).post(f"{URL}{count['id']}/approve/", {}, format="json")
    assert line_of(res.data, "CAB-12")["difference"] == "0.000"
    assert not Adjustment.objects.exists()  # sin diferencias, sin ajuste
    assert stock(cable, warehouse) == 8
    # Lo esperado queda guardado al aprobar: otra venta vieja que llegue después no lo cambia.
    sell(cable, warehouse, boss, 1, line.counted_at - timedelta(minutes=10))
    assert line_of(api(boss).get(f"{URL}{count['id']}/").data, "CAB-12")["expected"] == "8.000"


@pytest.mark.usefixtures("stocked")
def test_a_count_may_leave_negative_stock_flagged_for_review(helper, boss, warehouse, hammer):
    count = open_count(helper, warehouse, category=hammer.category_id)
    count_line(helper, count, "MAR-16", 3)
    line = CountLine.objects.get(pk=line_of(count, "MAR-16")["id"])
    sell(hammer, warehouse, boss, 9, line.counted_at + timedelta(seconds=1))  # quedan 1
    api(helper).post(f"{URL}{count['id']}/submit/")
    api(boss).post(f"{URL}{count['id']}/approve/", {}, format="json")
    assert stock(hammer, warehouse) == -6  # 1 − 7
    assert StockMovement.objects.get(kind="ADJUSTMENT").needs_review is True


def test_surplus_of_a_product_without_cost_enters_at_zero(helper, boss, warehouse, hammer):
    count = open_count(helper, warehouse, category=hammer.category_id)
    count_line(helper, count, "MAR-16", 4)
    api(helper).post(f"{URL}{count['id']}/submit/")
    assert api(boss).post(f"{URL}{count['id']}/approve/", {}, format="json").status_code == 200
    level = StockLevel.objects.get(product=hammer, warehouse=warehouse)
    assert (level.quantity, level.average_cost) == (Decimal("4.000"), Decimal("0.0000"))


# --- productos sin contar ----------------------------------------------------------

@pytest.mark.usefixtures("stocked")
def test_uncounted_products_are_not_adjusted_unless_marked_zero(helper, boss, warehouse, hammer, cable):
    count = open_count(helper, warehouse)
    count_line(helper, count, "MAR-16", 10)
    api(helper).post(f"{URL}{count['id']}/submit/")
    res = api(boss).post(f"{URL}{count['id']}/approve/", {}, format="json")
    assert line_of(res.data, "CAB-12")["counted"] is None
    assert stock(cable, warehouse) == 10 and not Adjustment.objects.exists()

    count = open_count(helper, warehouse)
    count_line(helper, count, "MAR-16", 10)
    api(helper).post(f"{URL}{count['id']}/submit/")
    res = api(boss).post(f"{URL}{count['id']}/approve/", {"zero_uncounted": [line_of(count, "CAB-12")["id"]]}, format="json")
    cable_line = line_of(res.data, "CAB-12")
    assert (cable_line["counted"], cable_line["marked_zero"], cable_line["difference"]) == ("0.000", True, "-10.000")
    assert stock(cable, warehouse) == 0


@pytest.mark.usefixtures("stocked")
def test_zero_all_uncounted(helper, boss, warehouse, hammer, cable):
    count = open_count(helper, warehouse)
    count_line(helper, count, "MAR-16", 10)
    api(helper).post(f"{URL}{count['id']}/submit/")
    assert api(boss).post(f"{URL}{count['id']}/approve/", {"zero_uncounted": "nada"}, format="json").status_code == 400
    api(boss).post(f"{URL}{count['id']}/approve/", {"zero_uncounted": "all"}, format="json")
    assert (stock(hammer, warehouse), stock(cable, warehouse)) == (10, 0)


# --- estados -----------------------------------------------------------------------

@pytest.mark.usefixtures("stocked")
def test_states(helper, boss, warehouse, hammer):
    count = open_count(helper, warehouse, category=hammer.category_id)
    res = api(helper).post(f"{URL}{count['id']}/submit/")
    assert res.status_code == 400 and "ningún producto" in str(res.data)
    assert api(boss).post(f"{URL}{count['id']}/approve/", {}, format="json").status_code == 400  # todavía abierto
    count_line(helper, count, "MAR-16", 9)
    count_line(helper, count, "MAR-16", 10)  # se puede volver a contar
    assert api(helper).post(f"{URL}{count['id']}/submit/").data["status"] == "SUBMITTED"
    assert count_line(helper, count, "MAR-16", 8).status_code == 400  # ya enviado
    assert api(boss).post(f"{URL}{count['id']}/void/", {"note": ""}, format="json").status_code == 400
    api(boss).post(f"{URL}{count['id']}/approve/", {}, format="json")
    res = api(boss).post(f"{URL}{count['id']}/void/", {"note": "x"}, format="json")
    assert res.status_code == 400 and "aprobado" in str(res.data)
    assert stock(hammer, warehouse) == 10  # contó lo mismo: sin ajuste


@pytest.mark.usefixtures("stocked")
def test_void_moves_nothing(helper, boss, warehouse, hammer):
    count = open_count(helper, warehouse, category=hammer.category_id)
    count_line(helper, count, "MAR-16", 2)
    res = api(boss).post(f"{URL}{count['id']}/void/", {"note": "Se contó mal todo"}, format="json")
    assert (res.data["status"], res.data["void_note"]) == ("VOIDED", "Se contó mal todo")
    assert stock(hammer, warehouse) == 10


# --- valor, listado y permisos --------------------------------------------------

@pytest.mark.usefixtures("stocked")
def test_value_of_the_difference_only_with_costs(helper, boss, make_user, warehouse, hammer):
    count = open_count(helper, warehouse, category=hammer.category_id)
    count_line(helper, count, "MAR-16", 7)
    assert line_of(api(boss).get(f"{URL}{count['id']}/").data, "MAR-16")["value"] is None
    owner = make_user("dueno", "Administrador")
    assert line_of(api(owner).get(f"{URL}{count['id']}/").data, "MAR-16")["value"] == "-60000.00"


@pytest.mark.usefixtures("stocked")
def test_list_and_permissions(helper, boss, make_user, warehouse, hammer):
    count = open_count(helper, warehouse, category=hammer.category_id)
    count_line(helper, count, "MAR-16", 7)
    rows = api(helper).get(URL, {"status": "OPEN"}).data
    assert [(r["number"], r["total"], r["counted"]) for r in rows] == [(count["number"], 1, 1)]
    assert "lines" not in rows[0]
    assert api(helper).get(URL, {"status": "APPROVED"}).data == []
    api(helper).post(f"{URL}{count['id']}/submit/")
    assert api(helper).post(f"{URL}{count['id']}/approve/", {}, format="json").status_code == 403
    assert api(helper).post(f"{URL}{count['id']}/void/", {"note": "x"}, format="json").status_code == 403
    seller = make_user("vende", "Ventas")
    assert api(seller).get(URL).status_code == 403
    assert APIClient().get(URL).status_code == 403


@pytest.mark.usefixtures("stocked")
def test_kardex_still_matches_stock(helper, boss, warehouse, hammer, cable):
    count = open_count(helper, warehouse)
    count_line(helper, count, "MAR-16", 7)
    count_line(helper, count, "CAB-12", 12.5)
    api(helper).post(f"{URL}{count['id']}/submit/")
    api(boss).post(f"{URL}{count['id']}/approve/", {}, format="json")
    for product, expected in ((hammer, 7), (cable, Decimal("12.5"))):
        total = StockMovement.objects.filter(product=product, warehouse=warehouse).aggregate(q=Sum("quantity"))["q"]
        assert total == stock(product, warehouse) == expected
