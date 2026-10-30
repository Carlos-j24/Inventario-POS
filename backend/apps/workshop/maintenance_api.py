"""API de mantenimientos (spec 012, T3). Todo con el módulo de taller activo.

- Planes: los ve recepción (para filtrar) y los crea o cambia quien maneja el catálogo (`catalog.edit`).
- Mantenimientos: la lista de lo que vence y avisar, ajustar o descartar son de recepción (`workshop.receive`).
"""
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.drf import require, require_any
from apps.catalog.models import Product

from . import maintenance
from .api import WorkshopEnabled
from .history import reminder_data
from .models import MaintenanceNotice, MaintenancePlan, MaintenanceReminder
from .order_api import _run

PLANS = "catalog.edit"
RECEIVE = "workshop.receive"


class SafePlanAccess(require_any(PLANS, RECEIVE)):
    """Ver los planes: catálogo o recepción. Crearlos o cambiarlos: solo catálogo."""

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True
        return request.user.has_app_permission(PLANS)


CAN_PLAN = [WorkshopEnabled, SafePlanAccess]
CAN_REMIND = [WorkshopEnabled, require(RECEIVE)]


class PlanSerializer(serializers.ModelSerializer):
    products = serializers.PrimaryKeyRelatedField(many=True, queryset=Product.objects.all())
    product_list = serializers.SerializerMethodField()

    class Meta:
        model = MaintenancePlan
        fields = ["id", "name", "every_km", "every_days", "products", "product_list", "is_active"]

    def get_product_list(self, plan):
        return [{"id": p.pk, "sku": p.sku, "name": p.name} for p in plan.products.all()]

    def validate_products(self, value):
        if not value:
            raise serializers.ValidationError("Elige al menos un producto o servicio que lo cumpla.")
        return value

    def validate(self, attrs):
        every_km = attrs.get("every_km", getattr(self.instance, "every_km", None))
        every_days = attrs.get("every_days", getattr(self.instance, "every_days", None))
        if every_km is None and every_days is None:
            raise serializers.ValidationError("Di cada cuántos km, cada cuántos días o las dos cosas.")
        for field, value in (("every_km", every_km), ("every_days", every_days)):
            if value is not None and value <= 0:
                raise serializers.ValidationError({field: "Debe ser mayor que cero."})
        return attrs


def plans():
    return MaintenancePlan.objects.prefetch_related("products")


class PlanListView(APIView):
    """Los planes (activos primero) o uno nuevo."""

    permission_classes = CAN_PLAN

    def get(self, request):
        rows = sorted(plans(), key=lambda p: (not p.is_active, p.name))
        return Response(PlanSerializer(rows, many=True).data)

    def post(self, request):
        data = PlanSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        plan = data.save()  # el nombre sin espacios, no vacío y sin repetir lo valida el serializer
        return Response(PlanSerializer(plans().get(pk=plan.pk)).data, status=status.HTTP_201_CREATED)


class PlanDetailView(APIView):
    """Cambia un plan; no se borra (tiene recordatorios): se desactiva."""

    permission_classes = CAN_PLAN

    def get(self, request, pk):
        return Response(PlanSerializer(get_object_or_404(plans(), pk=pk)).data)

    def patch(self, request, pk):
        data = PlanSerializer(get_object_or_404(MaintenancePlan, pk=pk), data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        data.save()
        return Response(PlanSerializer(plans().get(pk=pk)).data)


def row(reminder):
    """Una fila de la lista: el recordatorio, la moto y su dueño actual con su teléfono."""
    moto = reminder.motorcycle
    return {
        **reminder_data(reminder),
        "motorcycle": {"id": moto.pk, "plate": moto.plate, "vin": moto.vin, "brand": moto.brand, "model": moto.model,
                       "mileage": moto.mileage, "mileage_at": moto.mileage_at},
        "owner": {"id": moto.owner_id, "name": moto.owner.name, "phone": moto.owner.phone},
    }


def reminders():
    return MaintenanceReminder.objects.select_related(
        "plan", "source_order", "done_order", "motorcycle__owner",
    ).prefetch_related("notices__user", "motorcycle__mileage_readings")


class ReminderListView(APIView):
    """Lo que vence en la próxima semana o ya venció, los vencidos primero (?plan=, ?notified=1 con los avisados)."""

    permission_classes = CAN_REMIND

    def get(self, request):
        plan = None
        wanted = request.query_params.get("plan")
        if wanted:
            plan = MaintenancePlan.objects.filter(pk=wanted).first() if wanted.isdigit() else None
            if plan is None:
                return Response([])
        due = maintenance.due_reminders(plan=plan, include_notified=request.query_params.get("notified") == "1")
        return Response([row(reminder) for reminder, _ in due])


class NotifySerializer(serializers.Serializer):
    channel = serializers.ChoiceField(choices=MaintenanceNotice.Channel.choices)


class AdjustSerializer(serializers.Serializer):
    due_date = serializers.DateField(required=False, allow_null=True, default=None)
    due_mileage = serializers.IntegerField(required=False, allow_null=True, default=None)
    note = serializers.CharField(max_length=200, allow_blank=True)


class DismissSerializer(serializers.Serializer):
    note = serializers.CharField(max_length=200, allow_blank=True)


ACTIONS = {
    "notify": (NotifySerializer, maintenance.notify),
    "adjust": (AdjustSerializer, maintenance.adjust),
    "dismiss": (DismissSerializer, maintenance.dismiss),
}


class ReminderActionView(APIView):
    """POST /maintenance/<id>/<acción>/: notify, adjust o dismiss. Devuelve la fila."""

    permission_classes = CAN_REMIND

    def post(self, request, pk, action):
        if action not in ACTIONS:
            raise NotFound("Acción desconocida.")
        reminder = get_object_or_404(MaintenanceReminder, pk=pk)
        form, service = ACTIONS[action]
        data = form(data=request.data)
        data.is_valid(raise_exception=True)
        _run(service, reminder=reminder, user=request.user, **data.validated_data)
        return Response(row(reminders().get(pk=pk)))
