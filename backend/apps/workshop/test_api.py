"""API de motos (spec 009, T2)."""
import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Permission, Role
from apps.customers.models import Customer
from apps.customers.rules import FINAL_CONSUMER_NUMBER
from apps.invoicing.models import Business

from .models import Motorcycle
from .services import change_owner, register_motorcycle

pytestmark = pytest.mark.django_db
URL = "/api/workshop/motorcycles/"


@pytest.fixture
def clerk(make_user):
    return make_user("recepcion", "Recepción de taller")


@pytest.fixture(autouse=True)
def workshop_on(db):
    business = Business.load()
    business.workshop_enabled = True
    business.save()
    return business


@pytest.fixture
def api(clerk):
    client = APIClient()
    client.force_authenticate(clerk)
    return client


def customer(name="Don Jorge", number="79123456", phone="300 123-4567", **extra):
    return Customer.objects.create(id_type="13", id_number=number, name=name, phone=phone, **extra)


def moto(user, owner=None, **extra):
    data = {"plate": "XYZ12A", "brand": "Bajaj", "model": "Boxer CT 100", **extra}
    return register_motorcycle(user=user, owner=owner or customer(), **data)


NEW_CUSTOMER = {"id_type": "13", "id_number": "1.020.304.050", "name": "Ana Pérez", "phone": "3109998877"}


# --- Permisos ---

@pytest.mark.parametrize("role", ["Caja", "Ventas", "Jefe de bodega"])
def test_only_reception_can_use_it(make_user, clerk, role):
    client = APIClient()
    client.force_authenticate(make_user("otro", role))
    target = moto(clerk)
    assert client.get(URL).status_code == 403
    assert client.post(URL, {}, format="json").status_code == 403
    assert client.get(f"{URL}{target.pk}/").status_code == 403
    assert client.patch(f"{URL}{target.pk}/", {"color": "Rojo"}, format="json").status_code == 403
    assert client.post(f"{URL}{target.pk}/mileage/", {"mileage": 10}, format="json").status_code == 403
    assert client.post(f"{URL}{target.pk}/owner/", {"owner": target.owner_id}, format="json").status_code == 403


def test_with_the_module_off_it_does_not_exist(api, clerk, workshop_on, make_user):
    target = moto(clerk)
    workshop_on.workshop_enabled = False
    workshop_on.save()
    for response in (api.get(URL), api.post(URL, {}, format="json"), api.get(f"{URL}{target.pk}/"),
                     api.patch(f"{URL}{target.pk}/", {"color": "Rojo"}, format="json"),
                     api.post(f"{URL}{target.pk}/mileage/", {"mileage": 10}, format="json"),
                     api.post(f"{URL}{target.pk}/owner/", {"owner": target.owner_id}, format="json")):
        assert response.status_code == 404
    cashier = APIClient()
    cashier.force_authenticate(make_user("cajera", "Caja"))
    assert cashier.get(URL).status_code == 404  # ni siquiera "no tienes permiso": no existe


def test_me_says_whether_the_module_is_on(api, workshop_on):
    assert api.get("/api/auth/me/").data["workshop_enabled"] is True
    workshop_on.workshop_enabled = False
    workshop_on.save()
    assert api.get("/api/auth/me/").data["workshop_enabled"] is False


def test_the_administrator_can_use_it(make_user):
    client = APIClient()
    client.force_authenticate(make_user("jefe", "Administrador"))
    assert client.get(URL).status_code == 200


# --- Registrar (reglas 2 y 7) ---

def test_register_with_an_existing_customer(api, clerk):
    jorge = customer()
    response = api.post(URL, {"plate": "xyz-12a", "brand": "Bajaj", "model": "Boxer", "year": 2019,
                              "displacement_cc": 100, "color": "Negro", "mileage": 15200, "owner": jorge.pk}, format="json")
    assert response.status_code == 201, response.data
    body = response.data
    assert (body["plate"], body["owner"]["name"], body["mileage"]) == ("XYZ12A", "Don Jorge", 15200)
    assert [o["customer"]["id"] for o in body["ownerships"]] == [jorge.pk]
    assert body["mileage_readings"][0]["recorded_by"] == "recepcion"


def test_register_with_a_new_customer_in_the_same_step(api):
    response = api.post(URL, {"vin": "9FLPCJ200X1234567", "brand": "Honda", "customer": NEW_CUSTOMER}, format="json")
    assert response.status_code == 201, response.data
    ana = Customer.objects.get(id_number="1020304050")
    assert response.data["owner"]["id"] == ana.pk and ana.phone == "3109998877"


@pytest.mark.parametrize("phone", [None, "", "   "])
def test_a_new_customer_from_the_workshop_needs_a_phone(api, phone):
    data = {k: v for k, v in NEW_CUSTOMER.items() if k != "phone"}
    if phone is not None:
        data["phone"] = phone
    response = api.post(URL, {"plate": "ABC12D", "brand": "Honda", "customer": data}, format="json")
    assert response.status_code == 400 and "teléfono es obligatorio" in str(response.data)
    assert not Customer.objects.filter(id_number="1020304050").exists()


def test_a_bad_motorcycle_does_not_leave_the_new_customer_behind(api, clerk):
    moto(clerk)
    response = api.post(URL, {"plate": "XYZ 12A", "brand": "Honda", "customer": NEW_CUSTOMER}, format="json")
    assert response.status_code == 400
    assert response.data["plate"] == ["Ya existe una moto con esa placa."]
    assert not Customer.objects.filter(id_number="1020304050").exists()  # el cliente nuevo no queda a medias


def test_owner_or_customer_but_not_both_or_none(api):
    jorge = customer()
    for extra in ({}, {"owner": jorge.pk, "customer": NEW_CUSTOMER}):
        response = api.post(URL, {"plate": "ABC12D", "brand": "Honda", **extra}, format="json")
        assert response.status_code == 400 and "Elige un cliente registrado" in str(response.data["owner"])
    assert not Motorcycle.objects.exists()


def test_register_errors_come_by_field(api):
    final = Customer.objects.get(id_number=FINAL_CONSUMER_NUMBER)
    response = api.post(URL, {"brand": "Honda", "owner": customer().pk}, format="json")
    assert response.status_code == 400 and response.data["vin"] == ["Sin placa, el número de chasis es obligatorio."]
    response = api.post(URL, {"plate": "ABC12D", "brand": "Honda", "owner": final.pk}, format="json")
    assert response.status_code == 400 and "consumidor final" in response.data["owner"][0]
    response = api.post(URL, {"plate": "ABC12D", "brand": "Honda", "owner": customer("Sin tel", "1010", phone="").pk},
                        format="json")
    assert response.status_code == 400 and "necesita un teléfono" in response.data["owner"][0]
    response = api.post(URL, {"plate": "ABC12D", "brand": "Honda", "owner": customer("Otro", "2020").pk,
                              "mileage": -5}, format="json")
    assert response.status_code == 400 and "mileage" in response.data


# --- Buscar (regla 7) ---

def test_search_by_plate_vin_document_phone_or_name(api, clerk, make_user):
    boxer = moto(clerk)  # Don Jorge, cédula 79123456, teléfono "300 123-4567"
    honda = moto(clerk, owner=customer("Ana Pérez", "52111222", phone="+57 (310) 999.88.77"), plate="", vin="9FLPCJ200X1234567",
                 brand="Honda")
    found = lambda q: [m["id"] for m in api.get(URL, {"q": q}).data]  # noqa: E731
    assert found("xyz-1") == [boxer.pk]  # placa como sea que la escriban
    assert found("9flp") == [honda.pk]  # chasis
    assert found("7912") == [boxer.pk]  # cédula del dueño
    assert found("3001234567") == [boxer.pk]  # teléfono sin los separadores con que se guardó
    assert found("999 8877") == [honda.pk]
    assert found("pérez") == [honda.pk] and found("jorge") == [boxer.pk]
    assert found("57310") == [honda.pk]  # con indicativo y paréntesis
    assert found("KTM") == []
    assert found("12A") == [] and found("PCJ2") == []  # placa y chasis: empiezan por, no contienen
    assert found("9123") == []  # el documento también empieza por (79123456 lo contiene, no empieza)
    assert found("") == [honda.pk, boxer.pk]  # sin búsqueda: las más recientes primero


def test_inactive_motorcycles_only_on_request(api, clerk):
    old = moto(clerk)
    old.is_active = False
    old.save()
    assert api.get(URL, {"q": "XYZ"}).data == []
    assert [m["id"] for m in api.get(URL, {"q": "XYZ", "inactive": "1"}).data] == [old.pk]


def test_search_returns_at_most_20(api, clerk):
    owner = customer()
    for i in range(22):
        moto(clerk, owner=owner, plate=f"AAA{i:02d}")
    assert len(api.get(URL, {"q": "jorge"}).data) == 20
    assert len(api.get(URL).data) == 20


# --- Ficha y corrección ---

def test_detail_shows_owners_and_readings(api, clerk):
    jorge, ana = customer(), customer("Ana", "52111222")
    target = moto(clerk, owner=jorge, mileage=100)
    change_owner(motorcycle=target, new_owner=ana, user=clerk)
    body = api.get(f"{URL}{target.pk}/").data
    assert [o["customer"]["name"] for o in body["ownerships"]] == ["Ana", "Don Jorge"]
    assert body["ownerships"][1]["ended_at"] is not None and body["ownerships"][0]["ended_at"] is None
    assert body["owner"]["phone"] == "300 123-4567"
    assert api.get(f"{URL}999/").status_code == 404


def test_correct_the_data_but_not_owner_or_mileage(api, clerk):
    jorge = customer()
    target = moto(clerk, owner=jorge, mileage=500)
    response = api.patch(f"{URL}{target.pk}/", {"plate": "xyz-12b", "color": "Rojo", "year": 2020,
                                                "owner": customer("Ana", "52111222").pk, "mileage": 1}, format="json")
    assert response.status_code == 200, response.data
    target.refresh_from_db()
    assert (target.plate, target.color, target.year, target.brand) == ("XYZ12B", "Rojo", 2020, "Bajaj")
    assert (target.owner, target.mileage) == (jorge, 500)


def test_corrections_follow_the_rules(api, clerk):
    moto(clerk, plate="ABC12D", owner=customer("Otro", "2020"))
    target = moto(clerk)
    assert api.patch(f"{URL}{target.pk}/", {"plate": "abc 12d"}, format="json").data == {
        "plate": ["Ya existe una moto con esa placa."]}
    assert "vin" in api.patch(f"{URL}{target.pk}/", {"plate": ""}, format="json").data
    assert "year" in api.patch(f"{URL}{target.pk}/", {"year": 1900}, format="json").data
    assert api.patch(f"{URL}{target.pk}/", {"is_active": False}, format="json").data["is_active"] is False
    target.refresh_from_db()
    assert target.plate == "XYZ12A"


# --- Kilometraje y dueño ---

def test_mileage_goes_up_and_down_only_with_a_note(api, clerk):
    target = moto(clerk, mileage=1000)
    url = f"{URL}{target.pk}/mileage/"
    assert api.post(url, {"mileage": 1500}, format="json").data["mileage"] == 1500
    response = api.post(url, {"mileage": 900}, format="json")
    assert response.status_code == 400 and "solo sube" in response.data["mileage"][0]
    body = api.post(url, {"mileage": 900, "note": "Cambio de tablero"}, format="json").data
    assert body["mileage"] == 900 and body["mileage_readings"][0]["note"] == "Cambio de tablero"
    assert api.post(url, {"mileage": -1, "note": "x"}, format="json").status_code == 400
    assert api.post(f"{URL}999/mileage/", {"mileage": 1}, format="json").status_code == 404


def test_change_owner_to_an_existing_or_new_customer(api, clerk):
    jorge = customer()
    target = moto(clerk, owner=jorge)
    url = f"{URL}{target.pk}/owner/"
    response = api.post(url, {"owner": jorge.pk}, format="json")
    assert response.status_code == 400 and "ya es el dueño" in response.data["owner"][0]
    body = api.post(url, {"customer": NEW_CUSTOMER}, format="json").data
    assert body["owner"]["name"] == "Ana Pérez"
    assert [o["customer"]["name"] for o in body["ownerships"]] == ["Ana Pérez", "Don Jorge"]
    back = api.post(url, {"owner": jorge.pk}, format="json").data
    assert back["owner"]["id"] == jorge.pk and len(back["ownerships"]) == 3


def test_a_failed_owner_change_changes_nothing(api, clerk):
    target = moto(clerk)
    response = api.post(f"{URL}{target.pk}/owner/", {"customer": {**NEW_CUSTOMER, "id_number": "abc"}}, format="json")
    assert response.status_code == 400
    final = Customer.objects.get(id_number=FINAL_CONSUMER_NUMBER)
    response = api.post(f"{URL}{target.pk}/owner/", {"owner": final.pk}, format="json")
    assert response.status_code == 400
    target.refresh_from_db()
    assert target.ownerships.count() == 1


def test_the_detail_shows_the_last_20_readings(api, clerk):
    target = moto(clerk)
    for km in range(1, 23):
        api.post(f"{URL}{target.pk}/mileage/", {"mileage": km * 100}, format="json")
    readings = api.get(f"{URL}{target.pk}/").data["mileage_readings"]
    assert len(readings) == 20 and readings[0]["mileage"] == 2200  # la más reciente primero


# --- Clientes por teléfono (regla 3) ---

def test_reception_without_sales_can_still_find_and_register_customers(make_user):
    only = Role.objects.create(name="Solo recepción")
    only.permissions.set(Permission.objects.filter(code="workshop.receive"))
    client = APIClient()
    client.force_authenticate(make_user("solo", "Solo recepción"))
    assert client.get("/api/customers/", {"q": "ana"}).status_code == 200
    assert client.post("/api/customers/", NEW_CUSTOMER, format="json").status_code == 201



def test_customers_are_found_by_phone_too(clerk):
    client = APIClient()
    client.force_authenticate(clerk)
    jorge, ana = customer(), customer("Ana", "52111222", phone="+57 (310) 999.88.77")
    found = lambda q: [c["id"] for c in client.get("/api/customers/", {"q": q}).data]  # noqa: E731
    assert found("3001234567") == [jorge.pk]
    assert found("(310) 999") == [ana.pk]
    assert found("+57 310") == [ana.pk]
    assert found("5211") == [ana.pk]  # el documento sigue funcionando
    assert found("ana") == [ana.pk]
