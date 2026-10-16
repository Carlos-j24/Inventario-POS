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
