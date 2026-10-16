from django.contrib.auth import authenticate, login, logout
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework import generics, mixins, status, viewsets
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .drf import require
from .models import Permission, Role, User
from .serializers import LoginSerializer, MeSerializer, PermissionSerializer, RoleSerializer, UserSerializer


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
    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(generics.RetrieveAPIView):
    """Usuario actual con sus roles y permisos: la PWA los usa para mostrar u ocultar opciones."""

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
