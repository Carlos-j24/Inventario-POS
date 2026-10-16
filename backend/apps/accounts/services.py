"""Reglas de usuarios y roles que no dependen de la API."""
from django.core.exceptions import ValidationError

from .models import User

MANAGE = "users.manage"


def _codes(role, changed_role, changed_permissions):
    if changed_role is not None and role.pk == changed_role.pk:
        return {p.code for p in changed_permissions}
    return {p.code for p in role.permissions.all()}


def managers_left(*, user=None, active=True, roles=None, role=None, permissions=None):
    """Cuántos usuarios activos podrán administrar usuarios después de un cambio.

    El cambio se simula sin guardarlo: desactivar a `user` (active=False), cambiarle
    los roles (roles=[...]) o cambiar los permisos de `role` (permissions=[...]).
    """
    count = 0
    for u in User.objects.filter(is_active=True).prefetch_related("roles__permissions"):
        is_target = user is not None and u.pk == user.pk
        if is_target and not active:
            continue
        if u.is_superuser:
            count += 1
            continue
        user_roles = roles if is_target and roles is not None else u.roles.all()
        if any(MANAGE in _codes(r, role, permissions) for r in user_roles):
            count += 1
    return count


def ensure_someone_can_manage(**change):
    if managers_left(**change) == 0:
        raise ValidationError("El sistema debe conservar al menos un usuario activo que administre usuarios.")
