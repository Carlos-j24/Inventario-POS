"""API de ajustes de inventario (spec 006, T3)."""
from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.drf import require, require_any
from apps.catalog.models import QTY, Product, Unit

from . import adjustments as service
from .models import COST, Adjustment, AdjustmentLine, StockLevel, Warehouse

MONEY_PLACES = Decimal("0.01")


class LineInputSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    unit = serializers.SlugRelatedField(slug_field="code", queryset=Unit.objects.all(), required=False, allow_null=True)
    quantity = serializers.DecimalField(**QTY)
    direction = serializers.ChoiceField(choices=["IN", "OUT"])
    unit_cost = serializers.DecimalField(**COST, required=False, allow_null=True, min_value=0)


class AdjustmentInputSerializer(serializers.Serializer):
    client_uuid = serializers.UUIDField()
    warehouse = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.filter(is_active=True))
    reason = serializers.ChoiceField(choices=Adjustment.Reason.choices)
    note = serializers.CharField(allow_blank=True)
    lines = LineInputSerializer(many=True, allow_empty=False)


class LineSerializer(serializers.ModelSerializer):
    sku = serializers.CharField(source="product.sku", read_only=True)
    name = serializers.CharField(source="product.name", read_only=True)
    unit = serializers.CharField(source="unit.code", read_only=True)
    base_unit = serializers.CharField(source="product.base_unit.code", read_only=True)
    value = serializers.SerializerMethodField()

    class Meta:
        model = AdjustmentLine
        fields = ["id", "product", "sku", "name", "unit", "quantity", "base_quantity", "base_unit", "value"]

    def get_value(self, line):
        """Valor del ajuste al costo (negativo si sale). Solo con reports.costs, como el inventario valorizado."""
        if not self.context.get("show_costs"):
            return None
        if line.movement_id:
            cost = line.movement.unit_cost
        elif line.unit_cost is not None:
            cost = line.unit_cost
        else:
            level = self.context["levels"].get(line.product_id)
            cost = level.average_cost if level else Decimal(0)
        return str((line.base_quantity * (cost or 0)).quantize(MONEY_PLACES))


class AdjustmentSerializer(serializers.ModelSerializer):
    number = serializers.CharField(read_only=True)
    warehouse = serializers.CharField(source="warehouse.code", read_only=True)
    reason_label = serializers.CharField(source="get_reason_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    requested_by = serializers.CharField(source="requested_by.username", read_only=True)
    decided_by = serializers.CharField(source="decided_by.username", read_only=True, default=None)
    lines = LineSerializer(many=True, read_only=True)

    class Meta:
        model = Adjustment
        fields = [
            "id", "number", "client_uuid", "warehouse", "reason", "reason_label", "note", "status", "status_label",
            "requested_by", "created_at", "decided_by", "decided_at", "rejection_note", "lines",
        ]


def adjustments():
    return Adjustment.objects.select_related("warehouse", "requested_by", "decided_by").prefetch_related(
        Prefetch("lines", queryset=AdjustmentLine.objects.select_related("product__base_unit", "unit", "movement")),
    )


def serialize(request, rows, many=False):
    show_costs = request.user.has_app_permission("reports.costs")
    levels = {}
    if show_costs:
        items = rows if many else [rows]
        products = {line.product_id for a in items for line in a.lines.all()}
        warehouses = {a.warehouse_id for a in items}
        levels = {lv.product_id: lv for lv in StockLevel.objects.filter(product_id__in=products, warehouse_id__in=warehouses)}
    return AdjustmentSerializer(rows, many=many, context={"show_costs": show_costs, "levels": levels}).data


def _call(fn, **kwargs):
    try:
        return fn(**kwargs)
    except DjangoValidationError as exc:
        raise ValidationError(exc.messages)


class AdjustmentListView(APIView):
    """Ajustes (?status=PENDING|APPROVED|REJECTED), los más recientes primero, máximo 200. Crear: bodega."""

    permission_classes = [require_any(*service.REQUESTERS)]

    def get(self, request):
        rows = adjustments()
        wanted = request.query_params.get("status")
        if wanted in Adjustment.Status.values:
            rows = rows.filter(status=wanted)
        return Response(serialize(request, list(rows[:200]), many=True))

    def post(self, request):
        data = AdjustmentInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        adjustment, created = _call(service.create_adjustment, user=request.user, **data.validated_data)
        return Response(serialize(request, adjustments().get(pk=adjustment.pk)),
                        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class AdjustmentDetailView(APIView):
    permission_classes = [require_any(*service.REQUESTERS)]

    def get(self, request, pk):
        return Response(serialize(request, get_object_or_404(adjustments(), pk=pk)))


class AdjustmentApproveView(APIView):
    permission_classes = [require("inventory.adjust")]

    def post(self, request, pk):
        _call(service.approve_adjustment, adjustment=get_object_or_404(Adjustment, pk=pk), user=request.user)
        return Response(serialize(request, adjustments().get(pk=pk)))


class AdjustmentRejectView(APIView):
    permission_classes = [require("inventory.adjust")]

    def post(self, request, pk):
        _call(service.reject_adjustment, adjustment=get_object_or_404(Adjustment, pk=pk), user=request.user,
              note=request.data.get("note", ""))
        return Response(serialize(request, adjustments().get(pk=pk)))
