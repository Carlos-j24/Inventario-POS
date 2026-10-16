from rest_framework.permissions import BasePermission


def require(code):
    """Clase de permiso DRF que exige un código del catálogo: permission_classes = [require("inventory.receive")]."""

    class _HasAppPermission(BasePermission):
        message = f"No tienes el permiso '{code}'."

        def has_permission(self, request, view):
            user = request.user
            return bool(user and user.is_authenticated and user.has_app_permission(code))

    _HasAppPermission.__name__ = f"Require_{code.replace('.', '_')}"
    return _HasAppPermission


def require_any(*codes):
    """Como require(), pero basta con uno de los permisos: require_any("sales.create", "cash.operate")."""

    class _HasAnyAppPermission(BasePermission):
        message = f"Necesitas uno de estos permisos: {', '.join(codes)}."

        def has_permission(self, request, view):
            user = request.user
            if not (user and user.is_authenticated):
                return False
            granted = user.permission_codes()
            return any(code in granted for code in codes)

    _HasAnyAppPermission.__name__ = "RequireAny_" + "_".join(c.replace(".", "_") for c in codes)
    return _HasAnyAppPermission
