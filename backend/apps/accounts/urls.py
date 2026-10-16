from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import (
    CsrfView, LoginView, LogoutView, MeView, PasswordChangeView, PermissionListView, RoleViewSet, UserViewSet,
)

router = SimpleRouter()
router.register("users", UserViewSet, basename="user")
router.register("roles", RoleViewSet, basename="role")

auth_urlpatterns = [
    path("csrf/", CsrfView.as_view(), name="auth-csrf"),
    path("login/", LoginView.as_view(), name="auth-login"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
    path("me/", MeView.as_view(), name="auth-me"),
    path("password/", PasswordChangeView.as_view(), name="auth-password"),
]

urlpatterns = [
    path("permissions/", PermissionListView.as_view(), name="permission-list"),
    *router.urls,
]
