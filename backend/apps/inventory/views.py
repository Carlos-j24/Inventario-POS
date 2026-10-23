from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.drf import require

from .models import StockLevel, StockMovement, Warehouse
from .serializers import (
    ReceiptSerializer, StockLevelSerializer, StockMovementSerializer, WarehouseSerializer,
)
from .services import record_movement


class WarehouseListView(generics.ListAPIView):
    permission_classes = [require("inventory.view")]
    serializer_class = WarehouseSerializer
    queryset = Warehouse.objects.filter(is_active=True).order_by("-is_default", "code")  # la principal primero (spec 008)


class ReceiptView(APIView):
    """Entrada de mercancía a bodega."""

    permission_classes = [require("inventory.receive")]

    def post(self, request):
        data = ReceiptSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            movement, created = record_movement(
                kind=StockMovement.Kind.RECEIPT, user=request.user, **data.validated_data
            )
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages)
        return Response(
            StockMovementSerializer(movement).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class StockLevelListView(generics.ListAPIView):
    permission_classes = [require("inventory.view")]
    serializer_class = StockLevelSerializer
    queryset = StockLevel.objects.select_related("product", "warehouse")


class KardexView(generics.ListAPIView):
    """Movimientos de un producto, del más antiguo al más reciente."""

    permission_classes = [require("inventory.view")]
    serializer_class = StockMovementSerializer

    def get_queryset(self):
        qs = StockMovement.objects.filter(product_id=self.kwargs["product_id"])
        warehouse = self.request.query_params.get("warehouse")
        if warehouse:
            qs = qs.filter(warehouse__code=warehouse)
        return qs.select_related("product", "warehouse", "user")
