"""API de pedidos (spec 002). El cobro va por POST /api/sales/ con el campo order."""
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.drf import require, require_any

from .models import Order, business_date
from .orders import cancel_order, create_order, stock_warnings
from .serializers import OrderInputSerializer, OrderSerializer


def _orders():
    return Order.objects.select_related("salesperson", "sale").prefetch_related("lines__product", "lines__unit")


class OrderListCreateView(APIView):
    """GET: pedidos pendientes de hoy (?mine=1 solo los propios). POST: crear un pedido."""

    def get_permissions(self):
        # Ver la lista: el vendedor (sus pedidos) y la caja (para cobrar). Crear: solo con sales.create.
        perm = require("sales.create") if self.request.method == "POST" else require_any("sales.create", "cash.operate")
        return [perm()]

    def get(self, request):
        orders = _orders().filter(status=Order.Status.PENDING, business_date=business_date())
        if request.query_params.get("mine") == "1" or not request.user.has_app_permission("cash.operate"):
            orders = orders.filter(salesperson=request.user)  # sin caja, cada vendedor ve solo los suyos
        return Response(OrderSerializer(orders.order_by("created_at"), many=True).data)

    def post(self, request):
        data = OrderInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            order, created = create_order(user=request.user, **data.validated_data)
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages)
        body = OrderSerializer(order).data
        # Siempre con 3 decimales: SQLite y PostgreSQL devuelven la suma con distinta escala.
        body["warnings"] = [{**w, "available": f"{w['available']:.3f}"} for w in stock_warnings(order)]
        return Response(body, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class OrderByCodeView(generics.RetrieveAPIView):
    """La caja busca el pedido de hoy por su código de 4 dígitos (en cualquier estado, para explicar por qué no se cobra)."""

    permission_classes = [require("cash.operate")]
    serializer_class = OrderSerializer

    def get_object(self):
        return get_object_or_404(_orders(), code=self.kwargs["code"], business_date=business_date())


class OrderCancelView(APIView):
    permission_classes = [require("sales.create")]

    def post(self, request, pk):
        try:
            order = cancel_order(order=get_object_or_404(Order, pk=pk), user=request.user)
        except DjangoPermissionDenied as exc:
            raise PermissionDenied(str(exc))
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages)
        return Response(OrderSerializer(order).data)
