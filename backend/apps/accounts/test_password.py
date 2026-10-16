"""Spec 003, T2: cambiar la contraseña propia y contraseña temporal con cambio obligatorio."""
import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User

pytestmark = pytest.mark.django_db
OLD = "clave-de-prueba-123"
NEW = "Ferreteria-Nueva-2026!"


def api(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def session_client(username, password):
    """Cliente con sesión real (cookie), para comprobar que la sesión sigue tras cambiar la clave."""
    client = APIClient()
    assert client.login(username=username, password=password)
    return client


@pytest.fixture
def admin(make_user):
    return make_user("admin", "Administrador")


def create_by_admin(admin, username="pedro", roles=("Caja",)):
    res = api(admin).post("/api/accounts/users/", {
        "username": username, "password": "Temporal-2026!", "roles": list(roles),
    }, format="json")
    assert res.status_code == 201, res.data
    return User.objects.get(username=username)


# --- marca de contraseña temporal ---------------------------------------------------

def test_user_created_by_admin_must_change_password(admin):
    user = create_by_admin(admin)
    assert user.must_change_password
    assert api(admin).get(f"/api/accounts/users/{user.pk}/").data["must_change_password"] is True


def test_admin_reset_of_someone_else_is_temporary(admin, make_user):
    pedro = make_user("pedro", "Caja")
    api(admin).patch(f"/api/accounts/users/{pedro.pk}/", {"password": "Otra-Temporal-2026!"}, format="json")
    pedro.refresh_from_db()
    assert pedro.must_change_password


def test_admin_changing_own_password_is_not_temporary(admin, make_user):
    make_user("otro", "Administrador")
    api(admin).patch(f"/api/accounts/users/{admin.pk}/", {"password": "Mia-Definitiva-2026!"}, format="json")
    admin.refresh_from_db()
    assert not admin.must_change_password


def test_admin_cannot_clear_the_mark_directly(admin):
    user = create_by_admin(admin)
    api(admin).patch(f"/api/accounts/users/{user.pk}/", {"must_change_password": False}, format="json")
    user.refresh_from_db()
    assert user.must_change_password  # solo se quita cambiando la contraseña


# --- bloqueo de la API ---------------------------------------------------------------

def test_temporary_password_blocks_the_api_with_a_clear_message(admin, shift):
    user = create_by_admin(admin)
    client = api(user)
    res = client.get("/api/cash/registers/")
    assert res.status_code == 403
    assert "cambiar tu contraseña" in str(res.data["detail"])
    assert client.get("/api/catalog/products/").status_code == 403  # también lo que solo pide sesión


def test_temporary_password_still_allows_me_password_and_logout(admin):
    user = create_by_admin(admin)
    client = api(user)
    me = client.get("/api/auth/me/")
    assert me.status_code == 200
    assert me.data["must_change_password"] is True
    assert client.post("/api/auth/logout/").status_code == 204


def test_after_changing_password_the_api_works(admin, shift):
    user = create_by_admin(admin)
    client = session_client("pedro", "Temporal-2026!")
    res = client.post("/api/auth/password/", {"current_password": "Temporal-2026!", "new_password": NEW}, format="json")
    assert res.status_code == 200, res.data
    assert res.data["must_change_password"] is False
    # La sesión sigue abierta (no hay que volver a entrar) y la API ya responde.
    assert client.get("/api/cash/registers/").status_code == 200
    user.refresh_from_db()
    assert user.check_password(NEW)
    assert not user.must_change_password


# --- cambiar la contraseña propia ---------------------------------------------------

def test_any_user_changes_own_password(make_user):
    make_user("laura", "Caja")
    client = session_client("laura", OLD)
    res = client.post("/api/auth/password/", {"current_password": OLD, "new_password": NEW}, format="json")
    assert res.status_code == 200
    assert APIClient().login(username="laura", password=NEW)


@pytest.mark.parametrize("current, new, field", [
    ("equivocada", NEW, "current_password"),
    (OLD, OLD, "new_password"),         # igual a la actual
    (OLD, "123", "non_field_errors"),   # débil: validadores de Django
])
def test_bad_password_changes_are_rejected(make_user, current, new, field):
    laura = make_user("laura", "Caja")
    res = api(laura).post("/api/auth/password/", {"current_password": current, "new_password": new}, format="json")
    assert res.status_code == 400
    assert field in res.data
    laura.refresh_from_db()
    assert laura.check_password(OLD)


def test_password_change_needs_login():
    assert APIClient().post("/api/auth/password/", {"current_password": "x", "new_password": NEW}, format="json").status_code == 403


def test_guessing_current_password_is_rate_limited(make_user):
    laura = make_user("laura", "Caja")
    client = api(laura)
    codes = [
        client.post("/api/auth/password/", {"current_password": f"mala-{i}", "new_password": NEW}, format="json").status_code
        for i in range(6)
    ]
    assert codes[-1] == 429
