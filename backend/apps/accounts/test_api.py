import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Role, User

pytestmark = pytest.mark.django_db
PASSWORD = "clave-de-prueba-123"


def csrf_client():
    """Cliente que exige CSRF, como un navegador real."""
    client = APIClient(enforce_csrf_checks=True)
    client.get("/api/auth/csrf/")
    return client, client.cookies["csrftoken"].value


def admin_client(make_user):
    client = APIClient()
    client.force_authenticate(make_user("admin", "Administrador"))
    return client


# --- sesión -----------------------------------------------------------------

def test_login_returns_roles_and_permissions_and_opens_session(make_user):
    make_user("laura", "Caja")
    client, token = csrf_client()
    res = client.post(
        "/api/auth/login/", {"username": "laura", "password": PASSWORD}, format="json", HTTP_X_CSRFTOKEN=token
    )
    assert res.status_code == 200, res.data
    assert res.data["roles"] == ["Caja"]
    assert res.data["permissions"] == ["cash.operate", "sales.create"]
    assert client.get("/api/auth/me/").data["username"] == "laura"


def test_login_without_csrf_token_is_rejected(make_user):
    make_user("laura", "Caja")
    client, _ = csrf_client()
    res = client.post("/api/auth/login/", {"username": "laura", "password": PASSWORD}, format="json")
    assert res.status_code == 403


def test_wrong_password_is_rejected(make_user):
    make_user("laura", "Caja")
    client, token = csrf_client()
    res = client.post(
        "/api/auth/login/", {"username": "laura", "password": "otra"}, format="json", HTTP_X_CSRFTOKEN=token
    )
    assert res.status_code in (401, 403)
    assert client.get("/api/auth/me/").status_code == 403


def test_inactive_user_cannot_log_in(make_user):
    user = make_user("ex", "Caja")
    user.is_active = False
    user.save()
    client, token = csrf_client()
    res = client.post(
        "/api/auth/login/", {"username": "ex", "password": PASSWORD}, format="json", HTTP_X_CSRFTOKEN=token
    )
    assert res.status_code in (401, 403)


def test_login_attempts_are_limited(make_user):
    make_user("laura", "Caja")
    client, token = csrf_client()
    codes = [
        client.post(
            "/api/auth/login/", {"username": "laura", "password": "mala"}, format="json", HTTP_X_CSRFTOKEN=token
        ).status_code
        for _ in range(6)
    ]
    assert codes[-1] == 429


def test_logout_closes_session(make_user):
    make_user("laura", "Caja")
    client, token = csrf_client()
    client.post("/api/auth/login/", {"username": "laura", "password": PASSWORD}, format="json", HTTP_X_CSRFTOKEN=token)
    token = client.cookies["csrftoken"].value  # Django rota el token al iniciar sesión
    assert client.post("/api/auth/logout/", HTTP_X_CSRFTOKEN=token).status_code == 204
    assert client.get("/api/auth/me/").status_code == 403


def test_session_requests_need_csrf_for_writes(make_user):
    make_user("laura", "Caja")
    client, token = csrf_client()
    client.post("/api/auth/login/", {"username": "laura", "password": PASSWORD}, format="json", HTTP_X_CSRFTOKEN=token)
    assert client.post("/api/auth/logout/").status_code == 403


# --- usuarios y roles -------------------------------------------------------

def test_admin_creates_user_with_roles(make_user):
    res = admin_client(make_user).post("/api/accounts/users/", {
        "username": "pedro", "first_name": "Pedro", "password": "Ferreteria-2026!",
        "roles": ["Auxiliar de bodega"],
    }, format="json")
    assert res.status_code == 201, res.data
    assert "password" not in res.data
    pedro = User.objects.get(username="pedro")
    assert pedro.check_password("Ferreteria-2026!")
    assert pedro.permission_codes() == {"inventory.view", "inventory.receive", "inventory.count"}


def test_weak_password_is_rejected(make_user):
    res = admin_client(make_user).post(
        "/api/accounts/users/", {"username": "pedro", "password": "123", "roles": []}, format="json"
    )
    assert res.status_code == 400


def test_new_user_needs_password(make_user):
    res = admin_client(make_user).post("/api/accounts/users/", {"username": "pedro", "roles": []}, format="json")
    assert res.status_code == 400


def test_admin_changes_roles_and_password(make_user):
    pedro = make_user("pedro", "Auxiliar de bodega")
    res = admin_client(make_user).patch(f"/api/accounts/users/{pedro.pk}/", {
        "roles": ["Jefe de bodega"], "password": "Nueva-clave-2026!",
    }, format="json")
    assert res.status_code == 200, res.data
    pedro.refresh_from_db()
    assert pedro.has_app_permission("inventory.adjust")
    assert pedro.check_password("Nueva-clave-2026!")


def test_users_are_deactivated_not_deleted(make_user):
    pedro = make_user("pedro", "Caja")
    client = admin_client(make_user)
    assert client.delete(f"/api/accounts/users/{pedro.pk}/").status_code == 405
    assert client.patch(f"/api/accounts/users/{pedro.pk}/", {"is_active": False}, format="json").status_code == 200
    pedro.refresh_from_db()
    assert not pedro.is_active


def test_admin_cannot_deactivate_self(make_user):
    admin = make_user("admin", "Administrador")
    make_user("otro", "Administrador")
    client = APIClient()
    client.force_authenticate(admin)
    res = client.patch(f"/api/accounts/users/{admin.pk}/", {"is_active": False}, format="json")
    assert res.status_code == 400


def test_last_manager_cannot_lose_admin_role(make_user):
    admin = make_user("admin", "Administrador")
    client = APIClient()
    client.force_authenticate(admin)
    res = client.patch(f"/api/accounts/users/{admin.pk}/", {"roles": ["Caja"]}, format="json")
    assert res.status_code == 400
    make_user("segundo", "Administrador")
    res = client.patch(f"/api/accounts/users/{admin.pk}/", {"roles": ["Caja"]}, format="json")
    assert res.status_code == 200


def test_role_cannot_drop_users_manage_if_nobody_else_has_it(make_user):
    client = admin_client(make_user)
    admin_role = Role.objects.get(name="Administrador")
    codes = [c for c in admin_role.permissions.values_list("code", flat=True) if c != "users.manage"]
    res = client.patch(f"/api/accounts/roles/{admin_role.pk}/", {"permissions": codes}, format="json")
    assert res.status_code == 400


def test_admin_creates_custom_role(make_user):
    client = admin_client(make_user)
    res = client.post("/api/accounts/roles/", {
        "name": "Comprador", "permissions": ["inventory.view", "inventory.receive"],
    }, format="json")
    assert res.status_code == 201, res.data
    bad = client.post("/api/accounts/roles/", {"name": "X", "permissions": ["no.existe"]}, format="json")
    assert bad.status_code == 400


def test_permissions_catalog_is_listed(make_user):
    res = admin_client(make_user).get("/api/accounts/permissions/")
    assert {"code": "users.manage", "description": "Gestionar usuarios y roles"} in res.data


def test_only_users_manage_can_administer(make_user):
    client = APIClient()
    client.force_authenticate(make_user("marta", "Jefe de bodega"))
    assert client.get("/api/accounts/users/").status_code == 403
    assert client.post("/api/accounts/roles/", {"name": "X", "permissions": []}, format="json").status_code == 403
