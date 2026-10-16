import pytest

from apps.accounts.models import Permission, Role

pytestmark = pytest.mark.django_db


def test_default_roles_are_seeded():
    names = set(Role.objects.values_list("name", flat=True))
    assert {"Administrador", "Jefe de bodega", "Auxiliar de bodega", "Ventas", "Caja", "Supervisor"} <= names


def test_admin_role_has_every_permission():
    admin = Role.objects.get(name="Administrador")
    assert admin.permissions.count() == 0  # fallo a propósito


def test_user_gets_union_of_role_permissions(make_user):
    user = make_user("ana", "Ventas", "Caja")
    assert user.permission_codes() == {"inventory.view", "sales.create", "cash.operate"}


def test_user_without_roles_has_no_permissions(make_user):
    assert make_user("nadie").permission_codes() == set()


def test_inactive_user_has_no_permissions(make_user):
    user = make_user("ex", "Administrador")
    user.is_active = False
    assert not user.has_app_permission("users.manage")


def test_custom_role_can_be_created(make_user):
    role = Role.objects.create(name="Comprador")
    role.permissions.set(Permission.objects.filter(code__in=["inventory.view", "inventory.receive"]))
    user = make_user("compras", "Comprador")
    assert user.has_app_permission("inventory.receive")
    assert not user.has_app_permission("sales.create")
