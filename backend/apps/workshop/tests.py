"""Motos y dueños (spec 009, T1)."""
import itertools
from datetime import date

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import Client

from apps.accounts.models import Permission, Role
from apps.customers.models import Customer
from apps.customers.rules import FINAL_CONSUMER_NUMBER
from apps.invoicing.models import Business

from .models import MileageReading, Motorcycle, Ownership
from .services import change_owner, register_motorcycle, update_mileage

pytestmark = pytest.mark.django_db


@pytest.fixture
def clerk(make_user):
    return make_user("recepcion", "Recepción de taller")


def customer(name="Don Jorge", number="79123456", phone="3001234567", **extra):
    return Customer.objects.create(id_type="13", id_number=number, name=name, phone=phone, **extra)


_numbers = itertools.count(1)


def boxer(user, owner=None, **extra):
    data = {"plate": "xyz-12a", "brand": " Bajaj ", "model": "Boxer CT 100", **extra}
    return register_motorcycle(user=user, owner=owner or customer(number=f"9{next(_numbers):07d}"), **data)


# --- Datos de la moto (regla 4) ---

def test_the_plate_is_saved_clean_and_does_not_repeat(clerk):
    moto = boxer(clerk)
    assert (moto.plate, moto.brand) == ("XYZ12A", "Bajaj")
    for same in ("XYZ12A", "xyz 12a", "X.Y.Z-12A"):
        with pytest.raises(ValidationError, match="Ya existe una moto con esa placa"):
            boxer(clerk, plate=same)
    assert Motorcycle.objects.count() == 1


def test_without_a_plate_the_vin_is_required_and_does_not_repeat(clerk):
    with pytest.raises(ValidationError, match="Sin placa, el número de chasis es obligatorio"):
        boxer(clerk, plate="  ")
    new = boxer(clerk, plate="", vin="9fl-pcj2 00x1234567")
    assert (new.plate, new.vin) == ("", "9FLPCJ200X1234567")
    with pytest.raises(ValidationError, match="Ya existe una moto con ese número de chasis"):
        boxer(clerk, plate="", vin="9FLPCJ200X1234567")
    boxer(clerk, plate="", vin="9FLPCJ200X7654321")  # otra sin placa: sí
    assert Motorcycle.objects.count() == 2


def test_the_database_keeps_plate_and_vin_unique_and_one_of_them_present(clerk):
    owner = customer()
    boxer(clerk, owner=owner)
    for bad in (
        Motorcycle(plate="XYZ12A", brand="Honda", owner=owner),  # placa repetida
        Motorcycle(plate="", vin="", brand="Honda", owner=owner),  # ni placa ni chasis
    ):
        with pytest.raises(IntegrityError), transaction.atomic():
            Motorcycle.objects.bulk_create([bad])  # sin pasar por full_clean
    Motorcycle.objects.bulk_create([Motorcycle(plate="", vin="AAA111", brand="Honda", owner=owner),
                                    Motorcycle(plate="", vin="BBB222", brand="Honda", owner=owner)])  # varias sin placa


@pytest.mark.parametrize("field, value, message", [
    ("plate", "AB1", "La placa debe tener de 4 a 8"),
    ("plate", "ABC12D$", "La placa debe tener de 4 a 8"),
    ("plate", "ABCD12345", "La placa debe tener de 4 a 8"),
    ("vin", "AB123", "El chasis debe tener de 6 a 20"),
    ("year", 1949, "El año debe estar entre 1950"),
    ("year", date.today().year + 2, "El año debe estar entre 1950"),
    ("brand", "   ", "La marca es obligatoria"),
])
def test_invalid_data_is_rejected(clerk, field, value, message):
    with pytest.raises(ValidationError, match=message):
        boxer(clerk, **{field: value})


def test_valid_limits_are_accepted(clerk):
    moto = boxer(clerk, plate="ABC12", year=date.today().year + 1, vin="ABC123")  # placa vieja y año próximo
    assert boxer(clerk, plate="AB12").plate == "AB12"  # la más corta que se acepta
    assert (moto.plate, moto.vin) == ("ABC12", "ABC123")
    assert boxer(clerk, owner=customer("Otro", "1010"), plate="ABCD1234", year=1950, vin="V" * 20).plate == "ABCD1234"


# --- Dueños (reglas 2 y 6) ---

def test_registering_opens_the_first_ownership(clerk):
    owner = customer()
    moto = boxer(clerk, owner=owner)
    (ownership,) = moto.ownerships.all()
    assert (ownership.customer, ownership.ended_at, ownership.created_by) == (owner, None, clerk)
    assert moto.owner == owner and list(owner.motorcycles.all()) == [moto]


@pytest.mark.parametrize("problem, kwargs, message", [
    ("sin teléfono", {"phone": "  "}, "necesita un teléfono"),
    ("inactivo", {"is_active": False}, "está inactivo"),
])
def test_an_owner_needs_a_phone_and_must_be_active(clerk, problem, kwargs, message):
    with pytest.raises(ValidationError, match=message):
        boxer(clerk, owner=customer(**kwargs))
    assert not Motorcycle.objects.exists() and not Ownership.objects.exists()


def test_the_final_consumer_cannot_own_a_motorcycle(clerk):
    final = Customer.objects.get(id_number=FINAL_CONSUMER_NUMBER)
    final.phone = "3000000000"
    with pytest.raises(ValidationError, match="consumidor final no puede ser dueño"):
        boxer(clerk, owner=final)


def test_changing_the_owner_keeps_the_history(clerk, make_user):
    jorge, ana = customer(), customer("Ana", "52111222", phone="3109998877")
    moto = boxer(clerk, owner=jorge)
    other_clerk = make_user("recepcion2", "Recepción de taller")
    change_owner(motorcycle=moto, new_owner=ana, user=other_clerk)
    moto.refresh_from_db()
    assert moto.owner == ana
    current, previous = moto.ownerships.all()  # el más reciente primero
    assert (current.customer, current.ended_at, current.created_by) == (ana, None, other_clerk)
    assert previous.customer == jorge and previous.ended_at == current.started_at
    assert list(jorge.motorcycles.all()) == [] and list(ana.motorcycles.all()) == [moto]


def test_a_new_owner_must_be_valid_and_different(clerk):
    jorge = customer()
    moto = boxer(clerk, owner=jorge)
    with pytest.raises(ValidationError, match="ya es el dueño"):
        change_owner(motorcycle=moto, new_owner=jorge, user=clerk)
    with pytest.raises(ValidationError, match="necesita un teléfono"):
        change_owner(motorcycle=moto, new_owner=customer("Ana", "52111222", phone=""), user=clerk)
    moto.refresh_from_db()
    assert moto.owner == jorge and moto.ownerships.get().ended_at is None  # nada cambió


def test_the_database_allows_only_one_current_owner(clerk):
    moto = boxer(clerk)
    with pytest.raises(IntegrityError), transaction.atomic():
        Ownership.objects.create(motorcycle=moto, customer=customer("Ana", "52111222"), started_at=moto.created_at,
                                 created_by=clerk)


# --- Kilometraje (regla 5) ---

def test_the_first_mileage_is_recorded_only_if_given(clerk):
    assert not boxer(clerk).mileage_readings.exists()
    moto = boxer(clerk, owner=customer("Ana", "52111222"), plate="ABC12D", mileage=15200)
    (reading,) = moto.mileage_readings.all()
    assert (reading.mileage, reading.previous, reading.recorded_by) == (15200, None, clerk)
    assert moto.mileage_at == reading.recorded_at


def test_the_mileage_only_goes_up_unless_there_is_a_note(clerk):
    moto = boxer(clerk, mileage=15200)
    update_mileage(motorcycle=moto, mileage=18000, user=clerk)
    moto.refresh_from_db()
    assert moto.mileage == 18000
    for note in ("", "   "):
        with pytest.raises(ValidationError, match="solo sube \\(va en 18000 km\\)"):
            update_mileage(motorcycle=moto, mileage=17999, user=clerk, note=note)
    update_mileage(motorcycle=moto, mileage=18000, user=clerk)  # la misma lectura otra vez: sí
    update_mileage(motorcycle=moto, mileage=120, user=clerk, note=" Cambio de tablero ")
    moto.refresh_from_db()
    assert moto.mileage == 120
    latest = moto.mileage_readings.first()
    assert (latest.mileage, latest.previous, latest.note) == (120, 18000, "Cambio de tablero")
    assert moto.mileage_at == latest.recorded_at
    assert MileageReading.objects.filter(motorcycle=moto).count() == 4


def test_a_negative_mileage_is_rejected(clerk):
    moto = boxer(clerk)
    with pytest.raises(ValidationError, match="no puede ser negativo"):
        update_mileage(motorcycle=moto, mileage=-1, user=clerk, note="error")


# --- Permiso y rol (regla 1) ---

def test_the_reception_role_and_permission_exist():
    perm = Permission.objects.get(code="workshop.receive")
    reception = Role.objects.get(name="Recepción de taller")
    assert set(reception.permissions.values_list("code", flat=True)) == {"workshop.receive", "sales.create"}
    assert Role.objects.get(name="Administrador").permissions.filter(pk=perm.pk).exists()
    assert not Role.objects.get(name="Caja").permissions.filter(pk=perm.pk).exists()


# --- Admin de Django ---

@pytest.fixture
def admin_client(django_user_model):
    user = django_user_model.objects.create_superuser("jefe", password="clave-de-prueba-123")
    client = Client()
    client.force_login(user)
    return client, user


def admin_form(owner, **extra):
    return {"plate": "abc-12d", "vin": "", "brand": "Honda", "model": "CB 125F", "owner": owner.pk, "mileage": 500,
            "notes": "", "color": "", "is_active": "on",
            "ownerships-TOTAL_FORMS": 0, "ownerships-INITIAL_FORMS": 0,
            "mileage_readings-TOTAL_FORMS": 0, "mileage_readings-INITIAL_FORMS": 0, **extra}


def test_adding_from_the_admin_opens_the_ownership(admin_client):
    client, user = admin_client
    owner = customer()
    response = client.post("/admin/workshop/motorcycle/add/", admin_form(owner))
    assert response.status_code == 302
    moto = Motorcycle.objects.get()
    assert moto.plate == "ABC12D" and moto.mileage_at is not None
    assert moto.ownerships.get().created_by == user
    assert moto.mileage_readings.get().mileage == 500


def test_the_admin_applies_the_owner_rules_and_does_not_change_the_owner(admin_client):
    client, _ = admin_client
    response = client.post("/admin/workshop/motorcycle/add/", admin_form(customer(phone="")))
    assert response.status_code == 200 and "necesita un teléfono" in response.content.decode()
    assert not Motorcycle.objects.exists()
    jorge = customer("Jorge", "1010")
    client.post("/admin/workshop/motorcycle/add/", admin_form(jorge))
    moto = Motorcycle.objects.get()
    ana = customer("Ana", "52111222")
    response = client.post(f"/admin/workshop/motorcycle/{moto.pk}/change/", admin_form(
        ana, mileage=1, **{"ownerships-TOTAL_FORMS": 1, "ownerships-INITIAL_FORMS": 1,
                            "ownerships-0-id": moto.ownerships.get().pk, "ownerships-0-motorcycle": moto.pk,
                            "mileage_readings-TOTAL_FORMS": 1, "mileage_readings-INITIAL_FORMS": 1,
                            "mileage_readings-0-id": moto.mileage_readings.get().pk,
                            "mileage_readings-0-motorcycle": moto.pk},
    ))
    assert response.status_code == 302
    moto.refresh_from_db()
    assert (moto.owner, moto.mileage) == (jorge, 500)  # dueño y kilometraje no se cambian desde el admin


# --- Módulo de taller (regla 1) ---

def test_the_module_is_off_until_the_business_turns_it_on():
    business = Business.load()
    assert business.workshop_enabled is False  # una ferretería no ve nada del taller
    business.workshop_enabled = True
    business.save()
    assert Business.load().workshop_enabled is True
