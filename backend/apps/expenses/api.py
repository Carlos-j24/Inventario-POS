"""API de gastos (spec 013, T5). Todo con `expenses.manage` (decisión 8).

- /api/expenses/?from=&to=  lista del periodo (por defecto, el mes en curso) con su total; POST anota uno.
- /api/expenses/<id>/        ficha con su rastro; PATCH corrige.
- /api/expenses/<id>/void/   anula con motivo.
- /api/expenses/categories/  lista y crea categorías; /categories/<id>/ las renombra o desactiva.
"""
import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.drf import require
from apps.cash.models import CashRegister

from . import services as svc
from .models import Expense, ExpenseCategory

CAN_MANAGE = require("expenses.manage")


def _call(fn, **kwargs):
    try:
        return fn(**kwargs)
    except DjangoValidationError as exc:
        raise ValidationError(exc.message_dict if hasattr(exc, "error_dict") else exc.messages)


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpenseCategory
        fields = ["id", "name", "is_active"]


class ExpenseSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    register = serializers.SerializerMethodField()
    created_by = serializers.CharField(source="created_by.username", read_only=True)
    voided_by = serializers.CharField(source="voided_by.username", read_only=True, default=None)
    events = serializers.SerializerMethodField()

    class Meta:
        model = Expense
        fields = [
            "id", "spent_on", "amount", "category", "category_name", "note", "register", "status", "created_by",
            "created_at", "void_reason", "voided_by", "voided_at", "events",
        ]

    def get_register(self, obj):
        """La caja de cuyo cajón salió, y si su turno sigue abierto (si no, el valor ya no cambia)."""
        if obj.shift is None:
            return None
        return {"name": obj.shift.register.name, "shift_open": obj.shift.status == "OPEN"}

    def get_events(self, obj):
        return [
            {"kind": e.kind, "label": e.get_kind_display(), "detail": e.detail, "user": e.user.username, "at": e.at.isoformat()}
            for e in obj.events.all()
        ]


class NewExpenseSerializer(serializers.Serializer):
    spent_on = serializers.DateField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    category = serializers.PrimaryKeyRelatedField(queryset=ExpenseCategory.objects.all())
    note = serializers.CharField(max_length=200, allow_blank=True, required=False, default="")
    register = serializers.PrimaryKeyRelatedField(queryset=CashRegister.objects.filter(is_active=True), required=False, allow_null=True)


class ChangeExpenseSerializer(serializers.Serializer):
    spent_on = serializers.DateField(required=False)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    category = serializers.PrimaryKeyRelatedField(queryset=ExpenseCategory.objects.all(), required=False)
    note = serializers.CharField(max_length=200, allow_blank=True, required=False)


def _period(params):
    """?from=&to= (AAAA-MM-DD); sin fechas, el mes en curso."""
    today = timezone.localdate()
    try:
        start = datetime.date.fromisoformat(params["from"]) if params.get("from") else today.replace(day=1)
        end = datetime.date.fromisoformat(params["to"]) if params.get("to") else today
    except ValueError:
        raise ValidationError("Las fechas van como AAAA-MM-DD.")
    if start > end:
        raise ValidationError("La fecha inicial es posterior a la final.")
    return start, end


def _detail(expense):
    expense = (
        Expense.objects.select_related("category", "created_by", "voided_by", "shift__register")
        .prefetch_related("events__user").get(pk=expense.pk)
    )
    return ExpenseSerializer(expense).data


class ExpenseListView(APIView):
    permission_classes = [CAN_MANAGE]

    def get(self, request):
        start, end = _period(request.query_params)
        rows = (
            Expense.objects.filter(spent_on__range=(start, end))
            .select_related("category", "created_by", "voided_by", "shift__register")
            .prefetch_related("events__user")
        )
        active = [e for e in rows if e.status == Expense.Status.ACTIVE]
        return Response({
            "from": start.isoformat(), "to": end.isoformat(),
            "total": str(sum((e.amount for e in active), Decimal(0))),
            "expenses": ExpenseSerializer(rows, many=True).data,
        })

    def post(self, request):
        data = NewExpenseSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        expense = _call(svc.create_expense, user=request.user, **data.validated_data)
        return Response(_detail(expense), status=status.HTTP_201_CREATED)


class ExpenseDetailView(APIView):
    permission_classes = [CAN_MANAGE]

    def get(self, request, pk):
        return Response(_detail(get_object_or_404(Expense, pk=pk)))

    def patch(self, request, pk):
        expense = get_object_or_404(Expense, pk=pk)
        data = ChangeExpenseSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(_detail(_call(svc.update_expense, user=request.user, expense=expense, **data.validated_data)))


class ExpenseVoidView(APIView):
    permission_classes = [CAN_MANAGE]

    def post(self, request, pk):
        expense = get_object_or_404(Expense, pk=pk)
        reason = str(request.data.get("reason", ""))
        return Response(_detail(_call(svc.void_expense, user=request.user, expense=expense, reason=reason)))


class CategoryListView(generics.ListCreateAPIView):
    permission_classes = [CAN_MANAGE]
    serializer_class = CategorySerializer
    queryset = ExpenseCategory.objects.all()
    pagination_class = None


class CategoryDetailView(generics.UpdateAPIView):
    """Renombrar o desactivar. No se borran: los gastos anotados conservan su categoría."""

    permission_classes = [CAN_MANAGE]
    serializer_class = CategorySerializer
    queryset = ExpenseCategory.objects.all()
    http_method_names = ["patch"]
