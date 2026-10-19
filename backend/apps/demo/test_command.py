"""manage.py seed_demo: candados y contraseñas."""
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.accounts.models import User
from apps.catalog.models import Product
from apps.sales.models import Sale

from .seed import USERS

pytestmark = pytest.mark.django_db


def test_prints_a_different_random_password_per_user(settings):
    settings.DEBUG = True
    out = StringIO()
    call_command("seed_demo", stdout=out)
    lines = out.getvalue().splitlines()
    assert "Datos de demostración listos" in lines[0]
    secrets = {}
    for username, *_ in USERS:
        row = next(line.split() for line in lines[1:] if line.split()[0] == username)
        secrets[username] = row[1]
        assert User.objects.get(username=username).check_password(row[1])
    assert len(set(secrets.values())) == len(USERS)
    assert Sale.objects.exists()


def test_never_runs_without_debug(settings):
    settings.DEBUG = False
    with pytest.raises(CommandError, match="solo corre con DEBUG"):
        call_command("seed_demo")
    assert not Product.objects.exists()


def test_checks_the_password_and_existing_data(settings, hammer):
    settings.DEBUG = True
    with pytest.raises(CommandError, match="al menos 8"):
        call_command("seed_demo", password="corta")
    with pytest.raises(CommandError, match="La base ya tiene datos: usa --fresh"):
        call_command("seed_demo", password="Demo-clave-123")
    assert not User.objects.filter(username="admin.demo").exists()


def test_fresh_only_deletes_sqlite(settings, monkeypatch):
    settings.DEBUG = True
    from django.db import connection

    monkeypatch.setattr(connection, "vendor", "postgresql")
    with pytest.raises(CommandError, match="--fresh solo borra bases SQLite"):
        call_command("seed_demo", fresh=True)
