"""API de traslados entre bodegas (spec 006, T7)."""
from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.drf import require
from apps.catalog.models import QTY, Product, Unit

from . import transfers as service
from .models import Transfer, TransferLine, Warehouse

MONEY_PLACES = Decimal("0.01")
CAN_TRANSFER = require("inventory.transfer")


class LineInputSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    unit = serializers.SlugRelatedField(slug_field="code", queryset=Unit.objects.all(), required=False, allow_null=True)
    quantity = serializers.DecimalField(**QTY)


class TransferInputSerializer(serializers.Serializer):
    client_uuid = serializers.UUIDField()
    origin = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.all())
    destination = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.all())
    note = serializers.CharField(allow_blank=True, required=False, default="")
    lines = LineInputSerializer(many=True, allow_empty=False)


class LineSerializer(serializers.ModelSerializer):
    sku = serializers.CharField(source="product.sku", read_only=True)
    name = serializers.CharField(source="product.name", read_only=True)
    unit = serializers.CharField(source="unit.code", read_only=True)
    base_unit = serializers.CharField(source="product.base_unit.code", read_only=True)
    value = serializers.SerializerMethodField()

    class Meta:
        model = TransferLine
        fields = ["id", "product", "sku", "name", "unit", "quantity", "base_quantity", "base_unit", "value"]

    def get_value(self, line):
        """Valor movido al costo de salida. Solo con reports.costs, como el inventario valorizado."""
        if not self.context.get("show_costs"):
            return None
        return str((line.base_quantity * line.out_movement.unit_cost).quantize(MONEY_PLACES))


class TransferSerializer(serializers.ModelSerializer):
    number = serializers.CharField(read_only=True)
    origin = serializers.CharField(source="origin.code", read_only=True)
    destination = serializers.CharField(source="destination.code", read_only=True)
    created_by = serializers.CharField(source="created_by.username", read_only=True)
    lines = LineSerializer(many=True, read_only=True)

    class Meta:
        model = Transfer
        fields = ["id", "number", "client_uuid", "origin", "destination", "note", "created_by", "created_at", "lines"]


def transfers():
    return Transfer.objects.select_related("origin", "destination", "created_by").prefetch_related(
        Prefetch("lines", queryset=TransferLine.objects.select_related("product__base_unit", "unit", "out_movement")),
    )


def serialize(request, rows, many=False):
    context = {"show_costs": request.user.has_app_permission("reports.costs")}
    return TransferSerializer(rows, many=many, context=context).data


def _call(fn, **kwargs):
    try:
        return fn(**kwargs)
    except DjangoValidationError as exc:
        raise ValidationError(exc.messages)


class TransferListView(APIView):
    """Traslados, los más recientes primero, máximo 200 (?warehouse=<id>: los que salen de ella o entran)."""

    permission_classes = [CAN_TRANSFER]

    def get(self, request):
        rows = transfers()
        warehouse = request.query_params.get("warehouse", "")
        if warehouse.isdigit():
            rows = rows.filter(Q(origin_id=warehouse) | Q(destination_id=warehouse))
        return Response(serialize(request, list(rows[:200]), many=True))

    def post(self, request):
        data = TransferInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        transfer, created = _call(service.create_transfer, user=request.user, **data.validated_data)
        return Response(serialize(request, transfers().get(pk=transfer.pk)),
                        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class TransferDetailView(APIView):
    permission_classes = [CAN_TRANSFER]

    def get(self, request, pk):
        return Response(serialize(request, get_object_or_404(transfers(), pk=pk)))
