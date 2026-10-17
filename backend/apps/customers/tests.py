import pytest
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from .models import Customer
from .rules import check_digit, clean_customer

pytestmark = pytest.mark.django_db


# --- reglas ----------------------------------------------------------------

@pytest.mark.parametrize("nit, dv", [
    ("800197268", "4"),  # DIAN
    ("860034313", "7"),  # Davivienda
    ("900000009", "0"),  # residuo 0
    ("900000002", "1"),  # residuo 1
])
def test_check_digit(nit, dv):
    assert check_digit(nit) == dv


def data(**over):
    return {"id_type": "31", "id_number": "800197268", "person_type": "1", "name": "DIAN", **over}


def test_nit_is_normalized_and_gets_its_check_digit():
    cleaned = clean_customer(data(id_number="800.197.268", name="  Dirección   de Impuestos "))
    assert (cleaned["id_number"], cleaned["check_digit"], cleaned["name"]) == ("800197268", "4", "Dirección de Impuestos")
    assert clean_customer(data(id_number="800 197-268", check_digit="4"))["check_digit"] == "4"


@pytest.mark.parametrize("over, field", [
    ({"check_digit": "5"}, "check_digit"),
    ({"id_type": "13", "id_number": "10203040A", "person_type": "2"}, "id_number"),
    ({"id_type": "41", "id_number": "AB*123", "person_type": "2"}, "id_number"),
    ({"id_number": " . - "}, "id_number"),
    ({"id_type": "13", "id_number": "1020304050"}, "person_type"),  # jurídica con cédula
    ({"tax_responsibilities": ["O-13", "X-1"]}, "tax_responsibilities"),
    ({"name": "   "}, "name"),
    ({"id_number": "1234567890123456"}, "id_number"),  # más dígitos que pesos
])
def test_invalid_customer_data(over, field):
    with pytest.raises(ValidationError) as err:
        clean_customer(data(**over))
    assert field in err.value.message_dict


def test_only_nits_keep_a_check_digit():
    cc = clean_customer(data(id_type="13", id_number="1.020.304.050", person_type="2", check_digit="7"))
    assert (cc["id_number"], cc["check_digit"]) == ("1020304050", "")
    passport = clean_customer(data(id_type="41", id_number="ab12345", person_type="2"))
    assert passport["id_number"] == "AB12345"
    foreign = clean_customer(data(id_type="50", id_number="98765", check_digit="K"))
    assert foreign["check_digit"] == "K"  # NIT extranjero: se respeta el que traiga


def test_final_consumer_is_created_by_migration():
    fc = Customer.objects.get(id_number="222222222222")
    assert (fc.name, fc.id_type, fc.is_final_consumer, fc.tax_responsibilities) == ("Consumidor final", "13", True, ["R-99-PN"])


def test_model_clean_uses_the_same_rules():
    customer = Customer(id_type="31", id_number="860.034.313", person_type="1", name="Banco")
    customer.full_clean()
    assert (customer.id_number, customer.check_digit) == ("860034313", "7")


# --- API -------------------------------------------------------------------

def api(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.fixture
def cashier(make_user):
    return make_user("caja1", "Caja")


def test_cashier_registers_a_customer_with_its_check_digit(cashier):
    res = api(cashier).post("/api/customers/", {
        "id_type": "31", "id_number": "800.197.268", "person_type": "1", "name": "Ferreconstrucciones SAS",
        "email": "compras@ejemplo.co", "tax_responsibilities": ["O-15"],
    }, format="json")
    assert res.status_code == 201, res.data
    assert (res.data["id_number"], res.data["check_digit"], res.data["id_type_label"]) == ("800197268", "4", "NIT")
    assert res.data["is_final_consumer"] is False


def test_repeated_document_is_rejected_after_normalizing(cashier):
    Customer.objects.create(id_type="13", id_number="1020304050", name="Ana")
    res = api(cashier).post("/api/customers/", {"id_type": "13", "id_number": "1.020.304.050", "name": "Ana B"}, format="json")
    assert res.status_code == 400
    assert "id_number" in res.data
    # El mismo número con otro tipo de documento es otro cliente.
    assert api(cashier).post("/api/customers/", {"id_type": "22", "id_number": "1020304050", "name": "Ana C"}, format="json").status_code == 201


def test_wrong_check_digit_is_rejected(cashier):
    res = api(cashier).post("/api/customers/", {"id_type": "31", "id_number": "800197268", "check_digit": "1", "person_type": "1", "name": "X"}, format="json")
    assert res.status_code == 400
    assert "es 4" in str(res.data["check_digit"])


def test_search_by_document_prefix_or_name(cashier):
    Customer.objects.create(id_type="13", id_number="1020304050", name="Ana Gómez")
    Customer.objects.create(id_type="13", id_number="1020999999", name="Luis Pérez")
    Customer.objects.create(id_type="13", id_number="1020111111", name="Inactivo", is_active=False)
    client = api(cashier)
    assert [c["name"] for c in client.get("/api/customers/", {"q": "1.020"}).data] == ["Ana Gómez", "Luis Pérez"]
    assert [c["name"] for c in client.get("/api/customers/", {"q": "pérez"}).data] == ["Luis Pérez"]
    assert "Consumidor final" in [c["name"] for c in client.get("/api/customers/").data]


def test_search_returns_at_most_20(cashier):
    Customer.objects.bulk_create(Customer(id_type="13", id_number=f"10{i:08d}", name=f"Cliente {i:02d}") for i in range(25))
    assert len(api(cashier).get("/api/customers/", {"q": "10"}).data) == 20
    assert len(api(cashier).get("/api/customers/", {"q": "Cliente"}).data) == 20


def test_update_recomputes_check_digit_and_final_consumer_is_read_only(cashier):
    customer = Customer.objects.create(id_type="31", id_number="800197268", check_digit="4", person_type="1", name="DIAN")
    client = api(cashier)
    res = client.patch(f"/api/customers/{customer.pk}/", {"email": "nuevo@ejemplo.co"}, format="json")
    assert (res.status_code, res.data["check_digit"]) == (200, "4")
    res = client.patch(f"/api/customers/{customer.pk}/", {"id_number": "860034313"}, format="json")
    assert (res.data["id_number"], res.data["check_digit"]) == ("860034313", "7")

    fc = client.get("/api/customers/final-consumer/").data
    assert (fc["id_number"], fc["is_final_consumer"]) == ("222222222222", True)
    res = client.patch(f"/api/customers/{fc['id']}/", {"name": "Otro"}, format="json")
    assert res.status_code == 400
    assert Customer.objects.get(pk=fc["id"]).name == "Consumidor final"


def test_customers_need_cash_or_sales_permission(make_user):
    assert api(make_user("bodega", "Auxiliar de bodega")).get("/api/customers/").status_code == 403
    assert api(make_user("vende", "Ventas")).get("/api/customers/").status_code == 200
    assert APIClient().get("/api/customers/").status_code == 403
    assert api(make_user("bodega2", "Auxiliar de bodega")).post("/api/customers/", {}, format="json").status_code == 403
