from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework import generics, mixins, status, viewsets
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .drf import AllowWhilePasswordChange, require
from .models import Permission, Role, User
from .serializers import (
    LoginSerializer, MeSerializer, PasswordChangeSerializer, PermissionSerializer, RoleSerializer, UserSerializer,
)


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfView(APIView):
    """La PWA lo llama al arrancar para recibir la cookie csrftoken antes de iniciar sesión."""

    permission_classes = [AllowAny]

    def get(self, request):
        return Response(status=status.HTTP_204_NO_CONTENT)


@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    """Inicia sesión con cookie. Limitado a pocos intentos por minuto para frenar ataques de fuerza bruta."""

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        data = LoginSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        user = authenticate(request, **data.validated_data)
        if user is None:
            raise AuthenticationFailed("Usuario o contraseña incorrectos.")
        login(request, user)
        return Response(MeSerializer(user).data)


class LogoutView(APIView):
    permission_classes = [AllowWhilePasswordChange]

    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class PasswordChangeView(APIView):
    """Cambiar la contraseña propia. Pide la actual y quita la marca de contraseña temporal.

    Comparte el límite de intentos del inicio de sesión: adivinar la actual sería otro ataque de fuerza bruta.
    """

    permission_classes = [AllowWhilePasswordChange]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        data = PasswordChangeSerializer(data=request.data, context={"request": request})
        data.is_valid(raise_exception=True)
        user = request.user
        user.set_password(data.validated_data["new_password"])
        user.must_change_password = False
        user.save(update_fields=["password", "must_change_password"])
        update_session_auth_hash(request, user)  # la sesión actual sigue abierta
        return Response(MeSerializer(user).data)


class MeView(generics.RetrieveAPIView):
    """Usuario actual con sus roles y permisos: la PWA los usa para mostrar u ocultar opciones."""

    permission_classes = [AllowWhilePasswordChange]
    serializer_class = MeSerializer

    def get_object(self):
        return self.request.user


class PermissionListView(generics.ListAPIView):
    permission_classes = [require("users.manage")]
    serializer_class = PermissionSerializer
    queryset = Permission.objects.all()
    pagination_class = None


class UserViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                  mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Usuarios. No se borran: se desactivan (is_active=false) para conservar su historial."""

    permission_classes = [require("users.manage")]
    serializer_class = UserSerializer
    queryset = User.objects.prefetch_related("roles").order_by("username")


class RoleViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                  mixins.UpdateModelMixin, viewsets.GenericViewSet):
    permission_classes = [require("users.manage")]
    serializer_class = RoleSerializer
    queryset = Role.objects.prefetch_related("permissions")
