"""Bodega principal (spec 008, T1)."""
import importlib

import pytest
from django.apps import apps as django_apps
from django.db import IntegrityError, transaction
from rest_framework.test import APIClient

from .models import Warehouse

pytestmark = pytest.mark.django_db
URL = "/api/inventory/warehouses/"


def make(code, **extra):
    return Warehouse.objects.create(code=code, name=f"Bodega {code}", **extra)


def defaults():
    return list(Warehouse.objects.filter(is_default=True).values_list("code", flat=True))


def test_marking_another_one_unmarks_the_previous():
    loc, pral = make("LOC"), make("PRAL", is_default=True)
    assert defaults() == ["PRAL"]
    loc.is_default = True
    loc.save()
    assert defaults() == ["LOC"]
    pral.refresh_from_db()
    assert pral.is_default is False


def test_an_inactive_one_cannot_be_the_default():
    pral = make("PRAL", is_default=True)
    pral.is_active = False
    pral.save(update_fields=["is_active"])  # aunque solo se pida guardar is_active
    pral.refresh_from_db()
    assert (pral.is_active, pral.is_default) == (False, False)
    ghost = make("OLD", is_active=False, is_default=True)
    assert ghost.is_default is False and defaults() == []


def test_the_database_never_allows_two_defaults_or_an_inactive_default():
    make("PRAL", is_default=True)
    with pytest.raises(IntegrityError), transaction.atomic():
        Warehouse.objects.bulk_create([Warehouse(code="LOC", name="Local", is_default=True)])  # sin pasar por save
    with pytest.raises(IntegrityError), transaction.atomic():
        Warehouse.objects.bulk_create([Warehouse(code="OLD", name="Vieja", is_active=False, is_default=True)])


def test_api_brings_the_default_first_and_says_which_one(make_user):
    make("LOC")
    make("PRAL", is_default=True)
    make("OLD", is_active=False)
    client = APIClient()
    client.force_authenticate(make_user("pedro", "Auxiliar de bodega"))
    assert [(w["code"], w["is_default"]) for w in client.get(URL).data] == [("PRAL", True), ("LOC", False)]


@pytest.mark.parametrize("existing, expected", [
    ([("LOC", True), ("PRAL", True), ("ABC", True)], "PRAL"),  # PRAL si existe
    ([("LOC", True), ("BOD", True)], "BOD"),  # si no, la primera activa por código
    ([("PRAL", False), ("LOC", True)], "LOC"),  # una PRAL inactiva no cuenta
    ([("OLD", False)], None),  # ninguna activa: ninguna principal
    ([], None),
])
def test_the_migration_marks_pral_or_the_first_active(existing, expected):
    for code, active in existing:
        Warehouse.objects.create(code=code, name=code, is_active=active)
    migration = importlib.import_module("apps.inventory.migrations.0007_default_warehouse")
    migration.mark_default(django_apps, None)
    assert defaults() == ([expected] if expected else [])
