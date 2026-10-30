"""API de órdenes de trabajo (spec 011, T4). Todo con el módulo de taller activo.

Recepción (`workshop.receive`) ve todas las órdenes; el mecánico (`workshop.repair`) solo las que tiene
asignadas: las demás no existen para él (404). Qué puede hacer cada uno lo deciden los servicios de
work_orders.py; aquí solo se traducen sus errores (400 por reglas, 403 por permisos).
"""
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.drf import require_any
from apps.accounts.models import User
from apps.catalog.models import Product

from . import work_orders as svc
from .api import WorkshopEnabled, _call
from .history import reminder_data
from .models import Motorcycle, WorkOrder, WorkOrderApproval, WorkOrderEvent, WorkOrderLine

CAN_WORK = [WorkshopEnabled, require_any(svc.RECEIVE, svc.REPAIR)]
LISTED = 100


def person(user):
    return None if user is None else {"id": user.pk, "username": user.username, "name": user.get_full_name() or user.username}


class LineSerializer(serializers.ModelSerializer):
    sku = serializers.CharField(source="product.sku", read_only=True)
    name = serializers.CharField(source="product.name", read_only=True)
    total = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    taken = serializers.SerializerMethodField()
    returned = serializers.SerializerMethodField()
    added_by = serializers.CharField(source="added_by.username", read_only=True)

    class Meta:
        model = WorkOrderLine
        fields = ["id", "product", "sku", "name", "is_service", "quantity", "unit_price", "total", "approved",
                  "taken", "returned", "added_by", "created_at"]

    def get_taken(self, line):
        return line.movement_id is not None

    def get_returned(self, line):
        return line.returned_movement_id is not None


class ApprovalSerializer(serializers.ModelSerializer):
    recorded_by = serializers.CharField(source="recorded_by.username", read_only=True)

    class Meta:
        model = WorkOrderApproval
        fields = ["approved_by", "channel", "total", "recorded_by", "recorded_at"]


class EventSerializer(serializers.ModelSerializer):
    user = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = WorkOrderEvent
        fields = ["status", "note", "user", "at"]


class OrderSerializer(serializers.ModelSerializer):
    number = serializers.CharField(read_only=True)
    motorcycle = serializers.SerializerMethodField()
    customer = serializers.SerializerMethodField()
    mechanic = serializers.SerializerMethodField()

    class Meta:
        model = WorkOrder
        fields = ["id", "number", "status", "motorcycle", "customer", "mechanic", "mileage_in", "request", "received_at", "updated_at"]

    def get_motorcycle(self, order):
        moto = order.motorcycle
        return {"id": moto.pk, "plate": moto.plate, "vin": moto.vin, "brand": moto.brand, "model": moto.model}

    def get_customer(self, order):
        return {"id": order.customer.pk, "name": order.customer.name, "phone": order.customer.phone}

    def get_mechanic(self, order):
        return person(order.mechanic)


class OrderDetailSerializer(OrderSerializer):
    lines = LineSerializer(many=True, read_only=True)
    approvals = ApprovalSerializer(many=True, read_only=True)
    events = EventSerializer(many=True, read_only=True)
    received_by = serializers.CharField(source="received_by.username", read_only=True)
    charged_total = serializers.SerializerMethodField()
    pending_total = serializers.SerializerMethodField()
    till_order = serializers.SerializerMethodField()
    sale = serializers.SerializerMethodField()
    next_maintenance = serializers.SerializerMethodField()

    class Meta(OrderSerializer.Meta):
        fields = [*OrderSerializer.Meta.fields, "mileage_out", "condition", "diagnosis", "received_by", "lines",
                  "charged_total", "pending_total", "approvals", "events", "till_order", "sale", "next_maintenance"]

    def get_charged_total(self, order):
        return f"{svc.charged_total(order):.2f}"

    def get_pending_total(self, order):
        return f"{sum((line.total for line in order.lines.all() if not line.approved), 0):.2f}"

    def get_till_order(self, order):
        waiting = svc.till_order(order)
        return None if waiting is None else {"id": waiting.pk, "code": waiting.code, "total": f"{waiting.total:.2f}"}

    def get_sale(self, order):
        sale = svc.paid_sale(order)
        return None if sale is None else {"id": sale.pk, "number": sale.number, "total": f"{sale.total:.2f}"}

    def get_next_maintenance(self, order):
        """Los recordatorios que creó al entregarse (spec 012, T5)."""
        rows = order.reminders_created.select_related("plan", "source_order", "done_order", "motorcycle").prefetch_related(
            "notices__user", "motorcycle__mileage_readings",
        ).order_by("plan__name")
        return [reminder_data(r) for r in rows]


def orders():
    return WorkOrder.objects.select_related("motorcycle", "customer", "mechanic")


def visible(user):
    """Recepción ve todas; el mecánico, las suyas."""
    rows = orders()
    return rows if svc.is_reception(user) else rows.filter(mechanic=user)


def detail(order, status_code=status.HTTP_200_OK):
    order = orders().select_related("received_by").prefetch_related(
        Prefetch("lines", queryset=WorkOrderLine.objects.select_related("product", "added_by")),
        Prefetch("approvals", queryset=WorkOrderApproval.objects.select_related("recorded_by")),
        Prefetch("events", queryset=WorkOrderEvent.objects.select_related("user")),
    ).get(pk=order.pk)
    return Response(OrderDetailSerializer(order).data, status=status_code)


def _run(fn, **kwargs):
    """Como _call, y un permiso que niega el servicio como 403 con su mensaje."""
    try:
        return _call(fn, **kwargs)
    except DjangoPermissionDenied as exc:
        raise PermissionDenied(str(exc))


def mechanics():
    return User.objects.filter(is_active=True, roles__permissions__code=svc.REPAIR).distinct().order_by("username")


class ReceiveSerializer(serializers.Serializer):
    motorcycle = serializers.PrimaryKeyRelatedField(queryset=Motorcycle.objects.all())
    mileage = serializers.IntegerField(min_value=0)
    mileage_note = serializers.CharField(max_length=200, allow_blank=True, required=False, default="")
    request = serializers.CharField(allow_blank=True)
    condition = serializers.CharField(allow_blank=True, required=False, default="")
    mechanic = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False, allow_null=True, default=None)


class OrderListView(APIView):
    """Lista (?status=, por defecto las abiertas; ?status=ALL todas; ?mechanic=; ?motorcycle=) o recibe una moto."""

    permission_classes = CAN_WORK

    def get(self, request):
        rows = visible(request.user)
        wanted = request.query_params.get("status", "")
        if wanted == "ALL":
            pass
        elif wanted:
            if wanted not in WorkOrder.Status.values:
                raise ValidationError({"status": "Estado desconocido."})
            rows = rows.filter(status=wanted)
        else:
            rows = rows.filter(status__in=WorkOrder.OPEN)
        for field in ("mechanic", "motorcycle"):
            value = request.query_params.get(field)
            if value:
                rows = rows.filter(**{f"{field}_id": value}) if value.isdigit() else rows.none()
        return Response(OrderSerializer(rows[:LISTED], many=True).data)

    def post(self, request):
        data = ReceiveSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        order = _run(svc.receive_order, user=request.user, **data.validated_data)
        return detail(order, status.HTTP_201_CREATED)


class MechanicListView(APIView):
    """Los mecánicos activos, para asignar."""

    permission_classes = CAN_WORK

    def get(self, request):
        return Response([person(user) for user in mechanics()])


class OrderDetailView(APIView):
    permission_classes = CAN_WORK

    def get(self, request, pk):
        return detail(get_object_or_404(visible(request.user), pk=pk))


class AssignSerializer(serializers.Serializer):
    mechanic = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), allow_null=True)


class DiagnoseSerializer(serializers.Serializer):
    diagnosis = serializers.CharField(allow_blank=True)


class ApproveSerializer(serializers.Serializer):
    approved_by = serializers.CharField(max_length=120, allow_blank=True)
    channel = serializers.ChoiceField(choices=WorkOrderApproval.Channel.choices)


class DeliverSerializer(serializers.Serializer):
    mileage = serializers.IntegerField(min_value=0, required=False, allow_null=True, default=None)
    mileage_note = serializers.CharField(max_length=200, allow_blank=True, required=False, default="")


class CancelSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=200, allow_blank=True)


class Empty(serializers.Serializer):
    pass


# acción → (datos que pide, servicio)
ACTIONS = {
    "assign": (AssignSerializer, svc.assign_mechanic),
    "diagnose": (DiagnoseSerializer, svc.diagnose),
    "send-for-approval": (Empty, svc.send_for_approval),
    "approve": (ApproveSerializer, svc.approve),
    "ready": (Empty, svc.mark_ready),
    "send-to-till": (Empty, svc.send_to_till),
    "deliver": (DeliverSerializer, svc.deliver),
    "cancel": (CancelSerializer, svc.cancel),
}


class OrderActionView(APIView):
    """POST /orders/<id>/<acción>/ con los datos de la acción. Devuelve la ficha."""

    permission_classes = CAN_WORK

    def post(self, request, pk, action):
        if action not in ACTIONS:
            raise NotFound("Acción desconocida.")
        order = get_object_or_404(visible(request.user), pk=pk)
        form, service = ACTIONS[action]
        data = form(data=request.data)
        data.is_valid(raise_exception=True)
        _run(service, order=order, user=request.user, **data.validated_data)
        return detail(order)


class AddLineSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    quantity = serializers.DecimalField(max_digits=14, decimal_places=3)
    unit_price = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, allow_null=True, default=None)


class PriceSerializer(serializers.Serializer):
    unit_price = serializers.DecimalField(max_digits=14, decimal_places=2)


class LineListView(APIView):
    """Agrega un repuesto o mano de obra; queda por aprobar."""

    permission_classes = CAN_WORK

    def post(self, request, pk):
        order = get_object_or_404(visible(request.user), pk=pk)
        data = AddLineSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        _run(svc.add_line, order=order, user=request.user, **data.validated_data)
        return detail(order, status.HTTP_201_CREATED)


def _line(request, pk, line_id):
    order = get_object_or_404(visible(request.user), pk=pk)
    return order, get_object_or_404(WorkOrderLine, pk=line_id, work_order=order)


class LineDetailView(APIView):
    """PATCH pone el precio de la mano de obra; DELETE quita lo que no ha salido de la bodega."""

    permission_classes = CAN_WORK

    def patch(self, request, pk, line_id):
        order, line = _line(request, pk, line_id)
        data = PriceSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        _run(svc.set_price, line=line, user=request.user, **data.validated_data)
        return detail(order)

    def delete(self, request, pk, line_id):
        order, line = _line(request, pk, line_id)
        _run(svc.remove_line, line=line, user=request.user)
        return detail(order)


LINE_ACTIONS = {"take": svc.take_part, "return": svc.return_part}


class LineActionView(APIView):
    """POST .../lines/<id>/take/ saca el repuesto de la bodega; .../return/ lo regresa."""

    permission_classes = CAN_WORK

    def post(self, request, pk, line_id, action):
        if action not in LINE_ACTIONS:
            raise NotFound("Acción desconocida.")
        order, line = _line(request, pk, line_id)
        _run(LINE_ACTIONS[action], line=line, user=request.user)
        return detail(order)
