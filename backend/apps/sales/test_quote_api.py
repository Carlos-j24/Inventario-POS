"""API de cotizaciones (spec 007, T3)."""
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.inventory.models import StockMovement
from apps.inventory.services import record_movement
from apps.invoicing.models import Business

from .models import Order, Quote, business_date
from .services import create_sale

pytestmark = pytest.mark.django_db
URL = "/api/quotes/"


def api(user=None):
    client = APIClient()
    if user:
        client.force_authenticate(user)
    return client


@pytest.fixture
def vendor(make_user):
    return make_user("andres", "Ventas")


@pytest.fixture
def other(make_user):
    return make_user("camilo", "Ventas")


@pytest.fixture
def stocked(vendor, warehouse, hammer, cable):
    for product, qty in ((hammer, 50), (cable, 1000)):
        record_movement(kind=StockMovement.Kind.RECEIPT, product=product, warehouse=warehouse, quantity=qty, user=vendor)


def body(*lines, **extra):
    return {"client_uuid": str(uuid.uuid4()), "customer_name": "Don Jorge", "lines": list(lines), **extra}


def line(product, quantity, unit=None):
    item = {"product": product.pk, "quantity": str(quantity)}
    if unit:
        item["unit"] = unit
    return item


def create(user, *lines, **extra):
    res = api(user).post(URL, body(*lines, **extra), format="json")
    assert res.status_code == 201, res.data
    return res.data


# --- crear y ver ---------------------------------------------------------------------

def test_vendor_creates_a_quote_with_everything_to_print_it(vendor, hammer, cable):
    Business.objects.update_or_create(pk=1, defaults={"name": "Ferretería El Tornillo", "nit": "900123456", "check_digit": "8"})
    hammer.tax_rate, hammer.vat_excluded = "0", True
    hammer.save()
    payload = body(line(cable, 1, "rollo"), line(hammer, 2), customer_phone="3001234567", note="Entrega en obra", valid_days=15)
    res = api(vendor).post(URL, payload, format="json")
    assert res.status_code == 201, res.data
    q = res.data
    assert q["number"] == f"COT-{q['id']:06d}"
    assert (q["customer"], q["customer_phone"], q["note"], q["created_by"]) == ("Don Jorge", "3001234567", "Entrega en obra", "andres")
    assert (q["status"], q["status_label"], q["can_convert"]) == ("VALID", "Vigente", True)
    assert q["valid_until"] == str(business_date() + timedelta(days=15))
    assert [(l["sku"], l["unit"], l["unit_price"], l["total"], l["remaining"]) for l in q["lines"]] == [
        ("CAB-12", "rollo", "320000.00", "320000.00", "1.000"),
        ("MAR-16", "und", "28000.00", "56000.00", "2.000"),
    ]
    assert q["taxes"] == [
        {"rate": "19", "base": "268907.56", "tax": "51092.44"},
        {"rate": "excluido", "base": "56000.00", "tax": "0.00"},
    ]
    assert (q["subtotal"], q["tax"], q["total"]) == ("324907.56", "51092.44", "376000.00")
    assert (q["business"]["name"], q["business"]["nit"]) == ("Ferretería El Tornillo", "900123456-8")
    assert q["orders"] == []
    # Un reintento con el mismo client_uuid devuelve la misma.
    again = api(vendor).post(URL, payload, format="json")
    assert (again.status_code, again.data["id"], Quote.objects.count()) == (200, q["id"], 1)


def test_a_registered_customer_shows_its_document(vendor, hammer):
    from apps.customers.models import Customer

    builder = Customer.objects.create(id_number="900123456", check_digit="8", id_type="31", person_type="1", name="Constructora Los Pinos")
    q = create(vendor, line(hammer, 1), customer_name="", customer=builder.pk)
    assert (q["customer"], q["customer_id"], q["customer_document"]) == ("Constructora Los Pinos", builder.pk, "NIT 900123456-8")


@pytest.mark.parametrize("change, message", [
    ({"customer_name": ""}, "Escribe a nombre de quién va"),
    ({"valid_days": 31}, "La vigencia va de 1 a 30 días"),
    ({"inactive": True}, "MAR-16 no está a la venta"),
    ({"lines": []}, "lines"),
])
def test_invalid_quotes_are_400(vendor, hammer, change, message):
    if change.pop("inactive", False):
        hammer.is_active = False
        hammer.save()
    payload = {**body(line(hammer, 1)), **change}
    res = api(vendor).post(URL, payload, format="json")
    assert res.status_code == 400
    assert message in str(res.data)


# --- lista y permisos ------------------------------------------------------------------

def test_a_vendor_lists_their_own_unless_searching_the_exact_number(vendor, other, make_user, hammer):
    mine = create(vendor, line(hammer, 1), customer_name="Don Jorge")
    theirs = create(other, line(hammer, 1), customer_name="Doña Rosa")
    assert [q["number"] for q in api(vendor).get(URL).data] == [mine["number"]]
    assert api(vendor).get(URL, {"q": "rosa"}).data == []  # por nombre, solo entre las suyas
    assert [q["id"] for q in api(vendor).get(URL, {"q": theirs["number"]}).data] == [theirs["id"]]  # el cliente volvió con el número
    assert [q["id"] for q in api(vendor).get(URL, {"q": str(theirs["id"])}).data] == [theirs["id"]]
    assert api(vendor).get(f"{URL}{theirs['id']}/").status_code == 200

    boss = make_user("sofia", "Supervisor")
    assert [q["id"] for q in api(boss).get(URL).data] == [theirs["id"], mine["id"]]  # recientes primero
    assert api(boss).get(URL, {"mine": "1"}).data == []
    assert [q["id"] for q in api(make_user("marta", "Jefe de bodega")).get(URL).data] == [theirs["id"], mine["id"]]  # reports.view


def test_list_filters_by_effective_status(vendor, hammer):
    valid = create(vendor, line(hammer, 1))
    expired = create(vendor, line(hammer, 1))
    Quote.objects.filter(pk=expired["id"]).update(valid_until=business_date() - timedelta(days=1))
    assert [q["id"] for q in api(vendor).get(URL).data] == [valid["id"]]  # por defecto, las vigentes
    rows = api(vendor).get(URL, {"status": "EXPIRED"}).data
    assert [(q["id"], q["status"], q["status_label"]) for q in rows] == [(expired["id"], "EXPIRED", "Vencida")]
    assert len(api(vendor).get(URL, {"status": ""}).data) == 2
    assert api(vendor).get(f"{URL}{expired['id']}/").data["can_convert"] is False


def test_permissions(make_user, vendor, hammer):
    q = create(vendor, line(hammer, 1))
    helper = make_user("pedro", "Auxiliar de bodega")
    for method, path in (("get", URL), ("post", URL), ("get", f"{URL}{q['id']}/"), ("post", f"{URL}{q['id']}/order/"),
                         ("post", f"{URL}{q['id']}/duplicate/"), ("post", f"{URL}{q['id']}/void/")):
        assert getattr(api(helper), method)(path, {}, format="json").status_code == 403, (method, path)
        assert getattr(api(), method)(path, {}, format="json").status_code == 403
    boss = make_user("marta", "Jefe de bodega")  # ve y anula, pero no cotiza
    assert api(boss).post(URL, body(line(hammer, 1)), format="json").status_code == 403
    assert api(boss).post(f"{URL}{q['id']}/order/", {"client_uuid": str(uuid.uuid4())}, format="json").status_code == 403
    assert api(boss).post(f"{URL}{q['id']}/duplicate/", {"client_uuid": str(uuid.uuid4())}, format="json").status_code == 403
    assert api(make_user("laura", "Caja")).post(URL, body(line(hammer, 1)), format="json").status_code == 201  # la caja también vende
    assert api(vendor).get(f"{URL}999999/").status_code == 404


# --- anular y duplicar ------------------------------------------------------------------

def test_void_own_or_as_manager(vendor, other, make_user, hammer):
    q = create(vendor, line(hammer, 1))
    assert api(other).post(f"{URL}{q['id']}/void/", {"note": "No"}, format="json").status_code == 403
    res = api(vendor).post(f"{URL}{q['id']}/void/", {"note": " "}, format="json")
    assert (res.status_code, "Escribe por qué se anula" in str(res.data)) == (400, True)
    res = api(vendor).post(f"{URL}{q['id']}/void/", {"note": "Compró en otro lado"}, format="json")
    assert (res.status_code, res.data["status"], res.data["void_note"], res.data["voided_by"]) == (200, "VOIDED", "Compró en otro lado", "andres")
    theirs = create(other, line(hammer, 1))
    assert api(make_user("marta", "Jefe de bodega")).post(f"{URL}{theirs['id']}/void/", {"note": "Repetida"}, format="json").data["status"] == "VOIDED"


def test_duplicate_with_todays_prices(vendor, other, hammer, cable):
    old = create(vendor, line(hammer, 2), line(cable, 10))
    Quote.objects.filter(pk=old["id"]).update(valid_until=business_date() - timedelta(days=3))
    hammer.sale_price = Decimal("31000")
    hammer.save()
    cable.is_active = False
    cable.save()
    payload = {"client_uuid": str(uuid.uuid4()), "valid_days": 5}
    res = api(other).post(f"{URL}{old['id']}/duplicate/", payload, format="json")  # otro vendedor la renueva
    assert res.status_code == 201, res.data
    new = res.data
    assert (new["skipped"], new["duplicated_from"], new["created_by"], new["status"]) == (["CAB-12"], old["number"], "camilo", "VALID")
    assert [(l["sku"], l["unit_price"]) for l in new["lines"]] == [("MAR-16", "31000.00")]
    assert new["valid_until"] == str(business_date() + timedelta(days=5))
    assert api(other).post(f"{URL}{old['id']}/duplicate/", payload, format="json").status_code == 200


# --- convertir ------------------------------------------------------------------------

@pytest.mark.usefixtures("stocked")
def test_convert_by_parts_and_follow_it_in_the_detail(vendor, other, make_user, shift, hammer, cable):
    q = create(vendor, line(hammer, 10), line(cable, 2, "rollo"))
    hammers, rolls = q["lines"]
    hammer.sale_price = Decimal("31000")
    hammer.save()

    payload = {"client_uuid": str(uuid.uuid4()), "lines": [{"quote_line": hammers["id"], "quantity": "4"}]}
    res = api(other).post(f"{URL}{q['id']}/order/", payload, format="json")  # lo atiende otro vendedor
    assert res.status_code == 201, res.data
    order = res.data
    assert (order["status"], order["salesperson"], order["total"]) == ("PENDING", "camilo", "112000.00")  # 4 × 28.000 cotizado
    assert [(l["sku"], l["quantity"], l["unit_price"]) for l in order["lines"]] == [("MAR-16", "4.000", "28000.00")]
    assert 1000 <= order["code"] <= 9999 and order["warnings"] == []
    assert api(other).post(f"{URL}{q['id']}/order/", payload, format="json").status_code == 200  # reintento

    res = api(vendor).post(f"{URL}{q['id']}/order/", {"client_uuid": str(uuid.uuid4()), "lines": [{"quote_line": hammers["id"], "quantity": "7"}]}, format="json")
    assert (res.status_code, "MAR-16: quedan 6 und por convertir" in str(res.data)) == (400, True)

    detail = api(vendor).get(f"{URL}{q['id']}/").data
    assert [(l["in_orders"], l["charged"], l["remaining"]) for l in detail["lines"]] == [("4.000", "0.000", "6.000"), ("0.000", "0.000", "2.000")]
    assert [(o["code"], o["status"], o["sale_number"]) for o in detail["orders"]] == [(order["code"], "PENDING", None)]

    sale, _ = create_sale(user=make_user("laura", "Caja"), shift=shift, order=Order.objects.get(pk=order["id"]), lines=None,
                          client_uuid=uuid.uuid4(), payments=[{"method": "CASH", "amount": Decimal("200000")}])
    assert not sale.needs_review
    rest = api(vendor).post(f"{URL}{q['id']}/order/", {"client_uuid": str(uuid.uuid4())}, format="json").data  # todo lo que queda
    assert sorted((l["sku"], l["unit"], l["quantity"]) for l in rest["lines"]) == [("CAB-12", "rollo", "2.000"), ("MAR-16", "und", "6.000")]
    detail = api(vendor).get(f"{URL}{q['id']}/").data
    assert [(l["in_orders"], l["charged"], l["remaining"]) for l in detail["lines"]] == [("6.000", "4.000", "0.000"), ("2.000", "0.000", "0.000")]
    assert [o["sale_number"] for o in detail["orders"]] == [sale.number, None]


def test_convert_warns_about_stock_and_refuses_an_expired_quote(vendor, hammer):
    q = create(vendor, line(hammer, 3))  # sin existencias
    res = api(vendor).post(f"{URL}{q['id']}/order/", {"client_uuid": str(uuid.uuid4())}, format="json")
    assert res.status_code == 201
    assert res.data["warnings"] == [{"sku": "MAR-16", "name": "Martillo 16 oz", "kind": "sin_existencias", "available": "0.000"}]
    Order.objects.filter(pk=res.data["id"]).update(business_date=business_date() - timedelta(days=1))
    detail = api(vendor).get(f"{URL}{q['id']}/").data
    assert [o["status"] for o in detail["orders"]] == ["EXPIRED"]  # un pedido de ayer sin cobrar ya venció
    assert detail["lines"][0]["remaining"] == "3.000"  # y lo suyo vuelve a quedar por convertir
    expired = create(vendor, line(hammer, 1))
    Quote.objects.filter(pk=expired["id"]).update(valid_until=business_date() - timedelta(days=1))
    res = api(vendor).post(f"{URL}{expired['id']}/order/", {"client_uuid": str(uuid.uuid4())}, format="json")
    assert (res.status_code, "Duplícala" in str(res.data)) == (400, True)
