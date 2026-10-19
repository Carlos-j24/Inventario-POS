"""API de conteos físicos (spec 006, T5). Conteo ciego: lo esperado y la diferencia solo los ve quien
tiene inventory.adjust (quien aprueba); el valor de la diferencia, solo con reports.costs."""
from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.drf import require, require_any
from apps.catalog.models import QTY, Category, Unit

from . import counts as service
from .models import CountLine, PhysicalCount, StockLevel, Warehouse

MONEY_PLACES = Decimal("0.01")
QTY_PLACES = Decimal("0.001")


class OpenCountSerializer(serializers.Serializer):
    client_uuid = serializers.UUIDField()
    warehouse = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.filter(is_active=True))
    category = serializers.PrimaryKeyRelatedField(queryset=Category.objects.all(), required=False, allow_null=True)


class CountedSerializer(serializers.Serializer):
    quantity = serializers.DecimalField(**QTY)
    unit = serializers.SlugRelatedField(slug_field="code", queryset=Unit.objects.all(), required=False, allow_null=True)


class LineSerializer(serializers.ModelSerializer):
    sku = serializers.CharField(source="product.sku", read_only=True)
    name = serializers.CharField(source="product.name", read_only=True)
    barcode = serializers.CharField(source="product.barcode", read_only=True)
    base_unit = serializers.CharField(source="product.base_unit.code", read_only=True)
    units = serializers.SerializerMethodField()
    counted_by = serializers.CharField(source="counted_by.username", read_only=True, default=None)
    expected = serializers.SerializerMethodField()
    difference = serializers.SerializerMethodField()
    value = serializers.SerializerMethodField()

    class Meta:
        model = CountLine
        fields = [
            "id", "product", "sku", "name", "barcode", "base_unit", "units", "counted", "counted_at", "counted_by",
            "marked_zero", "expected", "difference", "value",
        ]

    def get_units(self, line):
        return [{"unit": u.unit.code, "factor": str(u.factor), "barcode": u.barcode} for u in line.product.units.all() if u.is_active]

    def _expected(self, line):
        if line.expected is not None:
            return line.expected  # ya aprobado: quedó guardado
        if line.counted is None:
            return None
        return service.expected_at(line.product, line.count.warehouse, line.counted_at)  # por aprobar: se calcula

    def get_expected(self, line):
        if not self.context.get("show_expected"):
            return None  # conteo ciego
        value = self._expected(line)
        return None if value is None else str(value.quantize(QTY_PLACES))

    def get_difference(self, line):
        if not self.context.get("show_expected"):
            return None
        expected = self._expected(line)
        return None if expected is None else str((line.counted - expected).quantize(QTY_PLACES))

    def get_value(self, line):
        if not (self.context.get("show_expected") and self.context.get("show_costs")):
            return None
        expected = self._expected(line)
        if expected is None:
            return None
        level = self.context["levels"].get(line.product_id)
        cost = level.average_cost if level else Decimal(0)
        return str(((line.counted - expected) * cost).quantize(MONEY_PLACES))


class CountSerializer(serializers.ModelSerializer):
    number = serializers.CharField(read_only=True)
    warehouse = serializers.CharField(source="warehouse.code", read_only=True)
    category = serializers.CharField(source="category.name", read_only=True, default=None)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    opened_by = serializers.CharField(source="opened_by.username", read_only=True)
    decided_by = serializers.CharField(source="decided_by.username", read_only=True, default=None)
    adjustment = serializers.CharField(source="adjustment.number", read_only=True, default=None)
    total = serializers.IntegerField(read_only=True)
    counted = serializers.IntegerField(read_only=True)

    class Meta:
        model = PhysicalCount
        fields = [
            "id", "number", "warehouse", "category", "status", "status_label", "opened_by", "created_at", "submitted_at",
            "decided_by", "decided_at", "void_note", "adjustment", "total", "counted",
        ]


class CountDetailSerializer(CountSerializer):
    lines = serializers.SerializerMethodField()

    class Meta(CountSerializer.Meta):
        fields = CountSerializer.Meta.fields + ["lines"]

    def get_lines(self, count):
        lines = count.lines.select_related("product__base_unit", "counted_by", "count__warehouse").prefetch_related("product__units__unit")
        return LineSerializer(lines, many=True, context=self.context).data


def counts():
    return PhysicalCount.objects.select_related("warehouse", "category", "opened_by", "decided_by", "adjustment").annotate(
        total=Count("lines"), counted=Count("lines", filter=Q(lines__counted__isnull=False)),
    )


def detail(request, pk):
    count = counts().get(pk=pk)
    show_costs = request.user.has_app_permission("reports.costs")
    levels = {}
    if show_costs:
        levels = {lv.product_id: lv for lv in StockLevel.objects.filter(warehouse=count.warehouse, product__in=count.lines.values("product"))}
    context = {"show_expected": request.user.has_app_permission("inventory.adjust"), "show_costs": show_costs, "levels": levels}
    return CountDetailSerializer(count, context=context).data


def _call(fn, **kwargs):
    try:
        return fn(**kwargs)
    except DjangoValidationError as exc:
        raise ValidationError(exc.messages)


class CountListView(APIView):
    """Conteos (?status=), los más recientes primero, máximo 100. Abrir: quien cuenta o aprueba."""

    permission_classes = [require_any(*service.COUNTERS)]

    def get(self, request):
        rows = counts()
        wanted = request.query_params.get("status")
        if wanted in PhysicalCount.Status.values:
            rows = rows.filter(status=wanted)
        return Response(CountSerializer(rows[:100], many=True).data)

    def post(self, request):
        data = OpenCountSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        count, created = _call(service.open_count, user=request.user, **data.validated_data)
        return Response(detail(request, count.pk), status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class CountDetailView(APIView):
    permission_classes = [require_any(*service.COUNTERS)]

    def get(self, request, pk):
        get_object_or_404(PhysicalCount, pk=pk)
        return Response(detail(request, pk))


class CountLineView(APIView):
    """Guarda lo contado de un producto (en la unidad que se elija)."""

    permission_classes = [require_any(*service.COUNTERS)]

    def patch(self, request, pk, line_id):
        count = get_object_or_404(PhysicalCount, pk=pk)
        line = get_object_or_404(CountLine, pk=line_id, count=count)
        data = CountedSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        _call(service.record_line, count=count, line=line, user=request.user, **data.validated_data)
        lines = detail(request, pk)["lines"]
        return Response(next(row for row in lines if row["id"] == line.pk))


class CountSubmitView(APIView):
    permission_classes = [require_any(*service.COUNTERS)]

    def post(self, request, pk):
        _call(service.submit_count, count=get_object_or_404(PhysicalCount, pk=pk))
        return Response(detail(request, pk))


class CountApproveView(APIView):
    """Aplica las diferencias. zero_uncounted: "all" o la lista de ids de líneas sin contar que van en 0."""

    permission_classes = [require("inventory.adjust")]

    def post(self, request, pk):
        zero = request.data.get("zero_uncounted") or []
        if zero != "all" and not (isinstance(zero, list) and all(isinstance(i, int) for i in zero)):
            raise ValidationError({"zero_uncounted": 'Usa "all" o una lista de ids de líneas.'})
        _call(service.approve_count, count=get_object_or_404(PhysicalCount, pk=pk), user=request.user, zero_uncounted=zero)
        return Response(detail(request, pk))


class CountVoidView(APIView):
    permission_classes = [require("inventory.adjust")]

    def post(self, request, pk):
        _call(service.void_count, count=get_object_or_404(PhysicalCount, pk=pk), user=request.user, note=request.data.get("note", ""))
        return Response(detail(request, pk))
