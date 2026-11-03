"""Gastos (spec 013, T5): se anotan, corrigen y anulan con rastro; los de la caja salen del arqueo."""
import datetime
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.test import APIClient

from apps.cash.services import close_shift, shift_summary

from . import services as svc
from .models import Expense, ExpenseCategory

pytestmark = pytest.mark.django_db
D = Decimal
URL = "/api/expenses/"


@pytest.fixture
def owner(make_user):
    return make_user("dueno", "Administrador")


@pytest.fixture
def soap(db):
    return ExpenseCategory.objects.get(name="Insumos")


@pytest.fixture
def rent(db):
    return ExpenseCategory.objects.get(name="Arriendo")


def today():
    return timezone.localdate()


def api(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def trail(expense):
    return [(e.kind, e.detail, e.user.username) for e in expense.events.all()]


# --- anotar ----------------------------------------------------------------------

def test_the_starting_categories_and_the_permission():
    assert list(ExpenseCategory.objects.values_list("name", flat=True)) == ["Arriendo", "Insumos", "Otros", "Servicios públicos", "Sueldos"]


def test_only_the_owner_manages_expenses(owner, make_user):
    assert owner.has_app_permission("expenses.manage")
    for role in ("Caja", "Recepción de taller", "Mecánico"):
        user = make_user(f"u-{role}", role)
        assert not user.has_app_permission("expenses.manage")
        assert api(user).get(URL).status_code == 403


def test_an_expense_is_noted_with_its_trail(owner, soap):
    expense = svc.create_expense(user=owner, spent_on=today(), amount=D("15000"), category=soap, note=" Jabón para el lavadero ")
    assert (expense.amount, expense.note, expense.shift, expense.status) == (D("15000"), "Jabón para el lavadero", None, "ACTIVE")
    assert trail(expense) == [("CREATED", "$15.000 en Insumos", "dueno")]


def test_what_is_not_a_valid_expense(owner, soap):
    with pytest.raises(ValidationError, match="positivo"):
        svc.create_expense(user=owner, spent_on=today(), amount=D("0"), category=soap)
    with pytest.raises(ValidationError, match="futura"):
        svc.create_expense(user=owner, spent_on=today() + datetime.timedelta(days=1), amount=D("1000"), category=soap)
    soap.is_active = False
    soap.save()
    with pytest.raises(ValidationError, match="desactivada"):
        svc.create_expense(user=owner, spent_on=today(), amount=D("1000"), category=soap)
    with transaction.atomic(), pytest.raises(IntegrityError):
        Expense.objects.create(spent_on=today(), amount=D("-1"), category=soap, created_by=owner)


# --- pagado de la caja -------------------------------------------------------------

def test_paid_from_the_till_comes_out_of_the_count(owner, soap, register, shift):
    assert shift_summary(shift)["expected_cash"] == D("100000")
    expense = svc.create_expense(user=owner, spent_on=today(), amount=D("15000"), category=soap, register=register)
    assert expense.shift == shift
    assert trail(expense) == [("CREATED", "$15.000 en Insumos, pagado de Caja 1", "dueno")]
    summary = shift_summary(shift)
    assert (summary["expenses"], summary["expected_cash"]) == (D("15000"), D("85000"))
    svc.create_expense(user=owner, spent_on=today(), amount=D("900000"), category=soap)  # no salió de la caja
    assert shift_summary(shift)["expected_cash"] == D("85000")
    closed = close_shift(shift=shift, user=owner, counted_cash=D("85000"))
    assert (closed.expected_cash, closed.difference) == (D("85000"), D("0"))


def test_from_the_till_needs_an_open_shift_and_today(owner, soap, register, shift):
    with pytest.raises(ValidationError, match="de hoy"):
        svc.create_expense(user=owner, spent_on=today() - datetime.timedelta(days=1), amount=D("1000"), category=soap, register=register)
    close_shift(shift=shift, user=owner, counted_cash=D("100000"))
    with pytest.raises(ValidationError, match="no tiene un turno abierto"):
        svc.create_expense(user=owner, spent_on=today(), amount=D("1000"), category=soap, register=register)


def test_a_voided_till_expense_goes_back_to_the_count(owner, soap, register, shift):
    expense = svc.create_expense(user=owner, spent_on=today(), amount=D("15000"), category=soap, register=register)
    svc.void_expense(user=owner, expense=expense, reason="Lo pagó el proveedor")
    assert shift_summary(shift)["expected_cash"] == D("100000")


def test_once_the_shift_closed_its_till_expenses_keep_their_value(owner, soap, rent, register, shift):
    expense = svc.create_expense(user=owner, spent_on=today(), amount=D("15000"), category=soap, register=register)
    close_shift(shift=shift, user=owner, counted_cash=D("85000"))
    with pytest.raises(ValidationError, match="ya cerró"):
        svc.update_expense(user=owner, expense=expense, amount=D("18000"))
    with pytest.raises(ValidationError, match="ya cerró"):
        svc.void_expense(user=owner, expense=expense, reason="Error")
    svc.update_expense(user=owner, expense=expense, category=rent, note="Era otra cosa")  # lo demás sí se corrige
    with pytest.raises(ValidationError, match="fecha de su turno"):
        svc.update_expense(user=owner, expense=expense, spent_on=today() - datetime.timedelta(days=1))


# --- corregir y anular -------------------------------------------------------------

def test_a_correction_leaves_what_changed(owner, soap, rent):
    expense = svc.create_expense(user=owner, spent_on=today(), amount=D("15000"), category=soap, note="Jabón")
    yesterday = today() - datetime.timedelta(days=1)
    svc.update_expense(user=owner, expense=expense, spent_on=yesterday, amount=D("18000"), category=rent, note="Arriendo bodega")
    expense.refresh_from_db()
    assert (expense.spent_on, expense.amount, expense.category, expense.note) == (yesterday, D("18000"), rent, "Arriendo bodega")
    assert trail(expense)[-1] == (
        "CHANGED",
        f"fecha {today():%Y-%m-%d} → {yesterday:%Y-%m-%d}; valor $15.000 → $18.000; categoría Insumos → Arriendo; "
        "nota «Jabón» → «Arriendo bodega»",
        "dueno",
    )
    svc.update_expense(user=owner, expense=expense, amount=D("18000"))  # sin cambios, sin rastro
    assert expense.events.count() == 2


def test_voiding_needs_a_reason_and_is_final(owner, soap):
    expense = svc.create_expense(user=owner, spent_on=today(), amount=D("15000"), category=soap)
    with pytest.raises(ValidationError, match="por qué"):
        svc.void_expense(user=owner, expense=expense, reason="  ")
    svc.void_expense(user=owner, expense=expense, reason="Anotado dos veces")
    expense.refresh_from_db()
    assert (expense.status, expense.void_reason, expense.voided_by) == ("VOIDED", "Anotado dos veces", owner)
    assert trail(expense)[-1] == ("VOIDED", "Anotado dos veces", "dueno")
    with pytest.raises(ValidationError, match="anulado"):
        svc.update_expense(user=owner, expense=expense, amount=D("1"))
    with pytest.raises(ValidationError, match="anulado"):
        svc.void_expense(user=owner, expense=expense, reason="Otra vez")


# --- API -----------------------------------------------------------------------------

def test_the_api_lists_the_month_with_its_total(owner, soap, rent, register, shift):
    client = api(owner)
    res = client.post(URL, {"spent_on": today().isoformat(), "amount": "15000", "category": soap.pk, "note": "Jabón",
                            "register": register.pk}, format="json")
    assert res.status_code == 201, res.data
    assert (res.data["register"], res.data["category_name"], res.data["events"][0]["label"]) == (
        {"name": "Caja 1", "shift_open": True}, "Insumos", "Anotado")
    other = client.post(URL, {"spent_on": today().isoformat(), "amount": "500000", "category": rent.pk}, format="json").data
    voided = client.post(URL, {"spent_on": today().isoformat(), "amount": "1000", "category": rent.pk}, format="json").data
    assert client.post(f"{URL}{voided['id']}/void/", {"reason": "Repetido"}, format="json").status_code == 200
    old = svc.create_expense(user=owner, spent_on=today().replace(day=1) - datetime.timedelta(days=1), amount=D("7"), category=rent)

    month = client.get(URL).data
    assert (month["from"], month["to"], month["total"]) == (today().replace(day=1).isoformat(), today().isoformat(), "515000.00")
    assert {e["id"] for e in month["expenses"]} == {res.data["id"], other["id"], voided["id"]}
    last_month = client.get(URL, {"from": old.spent_on.isoformat(), "to": old.spent_on.isoformat()}).data
    assert ([e["id"] for e in last_month["expenses"]], last_month["total"]) == ([old.pk], "7.00")
    assert client.get(URL, {"from": "2026-11-05", "to": "2026-11-01"}).status_code == 400


def test_the_api_corrects_voids_and_explains_errors(owner, soap, rent):
    client = api(owner)
    created = client.post(URL, {"spent_on": today().isoformat(), "amount": "15000", "category": soap.pk}, format="json").data
    res = client.patch(f"{URL}{created['id']}/", {"amount": "18000", "category": rent.pk}, format="json")
    assert res.status_code == 200, res.data
    assert (res.data["amount"], res.data["category_name"], res.data["events"][-1]["detail"]) == (
        "18000.00", "Arriendo", "valor $15.000 → $18.000; categoría Insumos → Arriendo")
    res = client.post(URL, {"spent_on": today().isoformat(), "amount": "-5", "category": soap.pk}, format="json")
    assert res.status_code == 400 and "positivo" in str(res.data)
    res = client.post(f"{URL}{created['id']}/void/", {"reason": ""}, format="json")
    assert res.status_code == 400 and "por qué" in str(res.data)


def test_the_owner_edits_the_categories(owner):
    client = api(owner)
    res = client.post(f"{URL}categories/", {"name": "Publicidad"}, format="json")
    assert res.status_code == 201, res.data
    res = client.patch(f"{URL}categories/{res.data['id']}/", {"name": "Publicidad y avisos", "is_active": False}, format="json")
    assert res.status_code == 200 and res.data == {"id": res.data["id"], "name": "Publicidad y avisos", "is_active": False}
    assert client.delete(f"{URL}categories/{res.data['id']}/").status_code == 405
    assert client.put(f"{URL}categories/{res.data['id']}/", {"name": "X", "is_active": True}, format="json").status_code == 405
    assert client.post(f"{URL}categories/", {"name": "Arriendo"}, format="json").status_code == 400  # ya existe
