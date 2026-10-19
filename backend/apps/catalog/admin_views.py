"""API para administrar el catálogo desde la app (spec 006, T1). Permiso catalog.edit; el precio y
el IVA exigen además catalog.edit_prices (lo valida catalog.services)."""
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.drf import require

from . import services
from .models import Category, PriceChange, Product, ProductUnit, Unit
from .serializers import (
    CategorySerializer, PresentationSerializer, PriceChangeSerializer, ProductAdminSerializer, UnitSerializer,
)

CAN_EDIT = require("catalog.edit")


def _call(fn, **kwargs):
    """Las reglas viven en catalog.services; sus errores salen como 400 con el campo cuando lo hay."""
    try:
        return fn(**kwargs)
    except DjangoValidationError as exc:
        raise ValidationError(exc.message_dict if hasattr(exc, "error_dict") else exc.messages)


def products():
    return Product.objects.select_related("category", "base_unit").prefetch_related(
        Prefetch("units", queryset=ProductUnit.objects.select_related("unit").order_by("unit__code")),
    )


class ProductAdminListView(APIView):
    """Productos activos e inactivos (?q= SKU, nombre o código de barras; ?category=; ?active=1|0). Máximo 200."""

    permission_classes = [CAN_EDIT]

    def get(self, request):
        rows = products()
        q = request.query_params.get("q", "").strip()
        if q:
            rows = rows.filter(
                Q(sku__icontains=q) | Q(name__icontains=q) | Q(barcode=q) | Q(units__barcode=q)
            ).distinct()
        if request.query_params.get("category"):
            rows = rows.filter(category_id=request.query_params["category"])
        active = request.query_params.get("active")
        if active in ("0", "1"):
            rows = rows.filter(is_active=active == "1")
        return Response(ProductAdminSerializer(rows.order_by("name")[:200], many=True).data)

    def post(self, request):
        data = ProductAdminSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        product = _call(services.create_product, user=request.user, data=data.validated_data)
        return Response(ProductAdminSerializer(products().get(pk=product.pk)).data, status=status.HTTP_201_CREATED)


class ProductAdminDetailView(APIView):
    permission_classes = [CAN_EDIT]

    def get(self, request, pk):
        return Response(ProductAdminSerializer(get_object_or_404(products(), pk=pk)).data)

    def patch(self, request, pk):
        product = get_object_or_404(Product, pk=pk)
        data = ProductAdminSerializer(product, data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        _call(services.update_product, user=request.user, product=product, data=data.validated_data)
        return Response(ProductAdminSerializer(products().get(pk=pk)).data)


class PresentationCreateView(APIView):
    """Agrega una presentación (rollo = 100 m) a un producto."""

    permission_classes = [CAN_EDIT]

    def post(self, request, pk):
        product = get_object_or_404(Product, pk=pk)
        data = PresentationSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        presentation = _call(services.add_presentation, 
            product=product, unit=data.validated_data["unit"], factor=data.validated_data["factor"],
            barcode=data.validated_data.get("barcode"),
        )
        return Response(PresentationSerializer(presentation).data, status=status.HTTP_201_CREATED)


class PresentationDetailView(APIView):
    permission_classes = [CAN_EDIT]

    def patch(self, request, pk):
        presentation = get_object_or_404(ProductUnit, pk=pk)
        data = PresentationSerializer(presentation, data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        fields = {k: v for k, v in data.validated_data.items() if k in ("factor", "barcode", "is_active")}
        return Response(PresentationSerializer(_call(services.update_presentation, presentation=presentation, data=fields)).data)

    def delete(self, request, pk):
        _call(services.delete_presentation, presentation=get_object_or_404(ProductUnit, pk=pk))
        return Response(status=status.HTTP_204_NO_CONTENT)


class CategoryListView(APIView):
    permission_classes = [CAN_EDIT]

    def get(self, request):
        return Response(CategorySerializer(Category.objects.all(), many=True).data)

    def post(self, request):
        category = _call(services.create_category, name=request.data.get("name", ""))
        return Response(CategorySerializer(category).data, status=status.HTTP_201_CREATED)


class CategoryDetailView(APIView):
    permission_classes = [CAN_EDIT]

    def patch(self, request, pk):
        category = _call(services.rename_category, category=get_object_or_404(Category, pk=pk), name=request.data.get("name", ""))
        return Response(CategorySerializer(category).data)

    def delete(self, request, pk):
        _call(services.delete_category, category=get_object_or_404(Category, pk=pk))
        return Response(status=status.HTTP_204_NO_CONTENT)


class UnitListView(generics.ListAPIView):
    permission_classes = [CAN_EDIT]
    serializer_class = UnitSerializer
    queryset = Unit.objects.all()
    pagination_class = None


class PriceHistoryView(generics.ListAPIView):
    permission_classes = [CAN_EDIT]
    serializer_class = PriceChangeSerializer
    pagination_class = None

    def get_queryset(self):
        return PriceChange.objects.filter(product_id=self.kwargs["pk"]).select_related("user")
