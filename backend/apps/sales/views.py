from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.drf import require

from .models import Sale
from .returns import create_return, mark_reviewed, void_sale
from .serializers import (
    ReturnInputSerializer, ReviewItemSerializer, ReviewSerializer, SaleInputSerializer, SaleReturnSerializer,
    SaleSerializer, VoidSerializer,
)
from .services import create_sale


class SaleCreateView(APIView):
    """Registra y cobra una venta en un turno de caja.

    Reenviar el mismo client_uuid devuelve la venta ya creada (200). Como incluye el cobro,
    exige cash.operate; el vendedor sin caja tendrá su flujo de pedidos más adelante.
    """

    permission_classes = [require("cash.operate")]

    def post(self, request):
        data = SaleInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            sale, created = create_sale(user=request.user, **data.validated_data)
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages)
        return Response(
            SaleSerializer(sale).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class SaleVoidView(APIView):
    """Anula una venta completa mientras su turno siga abierto."""

    permission_classes = [require("sales.void")]

    def post(self, request, pk):
        data = VoidSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            sale = void_sale(sale=get_object_or_404(Sale, pk=pk), user=request.user, **data.validated_data)
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages)
        return Response(SaleSerializer(sale).data)


class SaleReturnView(APIView):
    """Devolución total o parcial con reembolso desde un turno abierto. Idempotente por client_uuid."""

    permission_classes = [require("sales.void")]

    def post(self, request, pk):
        data = ReturnInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            sale_return, created = create_return(
                sale=get_object_or_404(Sale, pk=pk), user=request.user, **data.validated_data
            )
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages)
        return Response(
            SaleReturnSerializer(sale_return).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class ReviewListView(generics.ListAPIView):
    """Bandeja de ventas marcadas para revisión que nadie ha atendido todavía."""

    permission_classes = [require("reports.view")]
    serializer_class = ReviewItemSerializer
    pagination_class = None

    def get_queryset(self):
        return (
            Sale.objects.filter(needs_review=True, reviewed_at__isnull=True)
            .select_related("warehouse", "seller", "shift")
            .prefetch_related("lines__product", "lines__unit", "lines__movement", "payments")
            .order_by("created_at")
        )


class ReviewView(APIView):
    permission_classes = [require("reports.view")]

    def post(self, request, pk):
        data = ReviewSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            sale = mark_reviewed(sale=get_object_or_404(Sale, pk=pk), user=request.user, **data.validated_data)
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages)
        return Response(SaleSerializer(sale).data)


class SaleDetailView(generics.RetrieveAPIView):
    permission_classes = [require("sales.create")]
    serializer_class = SaleSerializer
    queryset = Sale.objects.select_related("warehouse", "seller").prefetch_related(
        "lines__product", "lines__unit", "payments"
    )
