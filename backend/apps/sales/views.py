import datetime
import re

from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.drf import require, require_any

from .models import Sale, business_date
from .returns import create_return, mark_reviewed, void_sale
from .serializers import (
    ReturnInputSerializer, ReviewItemSerializer, ReviewSerializer, SaleDetailSerializer, SaleInputSerializer,
    SaleListSerializer, SaleReturnSerializer, SaleSerializer, VoidSerializer,
)
from .services import create_sale


LIST_LIMIT = 200
_NUMBER = re.compile(r"^\s*(?:V-?)?0*(\d+)\s*$", re.IGNORECASE)


class SaleCreateView(APIView):
    """POST: registra y cobra una venta en un turno de caja (exige cash.operate).
    Reenviar el mismo client_uuid devuelve la venta ya creada (200).

    GET (spec 003): busca y lista ventas para el supervisor (sales.void o reports.view).
    Por defecto las de hoy; filtros ?number=V-000123, ?date=AAAA-MM-DD, ?register=<id>,
    ?status=COMPLETED|VOIDED y ?needs_review=1.
    """

    def get_permissions(self):
        if self.request.method == "GET":
            return [require_any("sales.void", "reports.view")()]
        return [require("cash.operate")()]

    def get(self, request):
        params = request.query_params
        sales = Sale.objects.select_related("shift__register", "seller", "salesperson", "order")
        number = params.get("number", "").strip()
        if number:
            match = _NUMBER.match(number)
            if not match:
                raise ValidationError({"number": "Escribe el número de la venta, por ejemplo V-000123."})
            sales = sales.filter(pk=int(match.group(1)))  # un número exacto se busca en cualquier fecha
        else:
            try:
                day = datetime.date.fromisoformat(params["date"]) if params.get("date") else business_date()
            except ValueError:
                raise ValidationError({"date": "Usa el formato AAAA-MM-DD."})
            sales = sales.filter(occurred_at__date=day)  # en hora de Bogotá (TIME_ZONE)
        if params.get("register"):
            sales = sales.filter(shift__register_id=params["register"])
        if params.get("status"):
            sales = sales.filter(status=params["status"])
        if params.get("needs_review") == "1":
            sales = sales.filter(needs_review=True)
        sales = sales.order_by("-occurred_at", "-pk")[:LIST_LIMIT]
        return Response(SaleListSerializer(sales, many=True).data)

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
    """Detalle con líneas, pagos, devoluciones y lo ya devuelto por línea (spec 003)."""

    permission_classes = [require_any("sales.create", "sales.void", "reports.view")]
    serializer_class = SaleDetailSerializer
    queryset = Sale.objects.select_related("warehouse", "seller", "salesperson", "shift__register", "order").prefetch_related(
        "lines__product", "lines__unit", "lines__return_lines", "payments", "returns__refund", "returns__lines",
    )
