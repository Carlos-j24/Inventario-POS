from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission, IsAuthenticated

PASSWORD_CHANGE_REQUIRED = "Debes cambiar tu contraseña temporal antes de continuar."


def _ready(user):
    """Con sesión y sin contraseña temporal pendiente (spec 003). Si la tiene, lo dice con claridad."""
    if not (user and user.is_authenticated):
        return False
    if getattr(user, "must_change_password", False):
        raise PermissionDenied(PASSWORD_CHANGE_REQUIRED)
    return True


class IsAuthenticatedAndReady(BasePermission):
    """Permiso por defecto de la API: sesión iniciada y contraseña definitiva."""

    def has_permission(self, request, view):
        return _ready(request.user)


class AllowWhilePasswordChange(IsAuthenticated):
    """Para lo único que puede hacer un usuario con contraseña temporal: saber quién es, cambiarla y salir."""


def require(code):
    """Clase de permiso DRF que exige un código del catálogo: permission_classes = [require("inventory.receive")]."""

    class _HasAppPermission(BasePermission):
        message = f"No tienes el permiso '{code}'."

        def has_permission(self, request, view):
            return _ready(request.user) and request.user.has_app_permission(code)

    _HasAppPermission.__name__ = f"Require_{code.replace('.', '_')}"
    return _HasAppPermission


def require_any(*codes):
    """Como require(), pero basta con uno de los permisos: require_any("sales.create", "cash.operate")."""

    class _HasAnyAppPermission(BasePermission):
        message = f"Necesitas uno de estos permisos: {', '.join(codes)}."

        def has_permission(self, request, view):
            if not _ready(request.user):
                return False
            granted = request.user.permission_codes()
            return any(code in granted for code in codes)

    _HasAnyAppPermission.__name__ = "RequireAny_" + "_".join(c.replace(".", "_") for c in codes)
    return _HasAnyAppPermission
