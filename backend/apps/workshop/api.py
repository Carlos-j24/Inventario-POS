"""API de motos y dueños (spec 009, T2). Todo con el módulo de taller activo y workshop.receive.

La ficha de la moto lista sus órdenes de trabajo (spec 011, regla 11) y, desde la spec 012, su historial
(lo que se le hizo en cada orden entregada) y sus recordatorios de mantenimiento. Las órdenes tienen su
API en order_api.py y los mantenimientos en maintenance_api.py.
"""
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.drf import require
from apps.customers.models import Customer
from apps.customers.queries import number_or_phone, only_digits, phone_digits
from apps.customers.serializers import CustomerSerializer
from apps.invoicing.models import Business

from . import history, services
from .models import MileageReading, Motorcycle, Ownership, WorkOrder
from .rules import normalize_code



class WorkshopEnabled(BasePermission):
    """Con el módulo de taller apagado (la ferretería), la API del taller no existe: 404 para todos."""

    def has_permission(self, request, view):
        if not Business.load().workshop_enabled:
            raise NotFound("El módulo de taller no está activo.")
        return True


CAN_RECEIVE = [WorkshopEnabled, require("workshop.receive")]
EDITABLE = ["plate", "vin", "brand", "model", "year", "displacement_cc", "color", "notes", "is_active"]
READINGS_SHOWN = 20


class OwnerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ["id", "name", "id_type", "id_number", "check_digit", "phone"]


class OwnershipSerializer(serializers.ModelSerializer):
    customer = OwnerSerializer(read_only=True)

    class Meta:
        model = Ownership
        fields = ["customer", "started_at", "ended_at"]


class ReadingSerializer(serializers.ModelSerializer):
    recorded_by = serializers.CharField(source="recorded_by.username", read_only=True)

    class Meta:
        model = MileageReading
        fields = ["mileage", "previous", "note", "recorded_at", "recorded_by"]


class MotorcycleSerializer(serializers.ModelSerializer):
    owner = OwnerSerializer(read_only=True)

    class Meta:
        model = Motorcycle
        fields = ["id", *EDITABLE, "mileage", "mileage_at", "owner", "created_at", "updated_at"]


class WorkOrderSummarySerializer(serializers.ModelSerializer):
    number = serializers.CharField(read_only=True)

    class Meta:
        model = WorkOrder
        fields = ["id", "number", "status", "mileage_in", "request", "received_at"]


class MotorcycleDetailSerializer(MotorcycleSerializer):
    ownerships = OwnershipSerializer(many=True, read_only=True)
    mileage_readings = serializers.SerializerMethodField()
    work_orders = WorkOrderSummarySerializer(many=True, read_only=True)
    history = serializers.SerializerMethodField()
    reminders = serializers.SerializerMethodField()

    class Meta(MotorcycleSerializer.Meta):
        fields = [*MotorcycleSerializer.Meta.fields, "ownerships", "mileage_readings", "work_orders", "history", "reminders"]

    def get_history(self, motorcycle):
        return history.motorcycle_history(motorcycle)

    def get_reminders(self, motorcycle):
        return history.motorcycle_reminders(motorcycle)

    def get_mileage_readings(self, motorcycle):
        return ReadingSerializer(motorcycle.mileage_readings.all()[:READINGS_SHOWN], many=True).data


class DataSerializer(serializers.Serializer):
    """Los datos de la moto que se escriben; las reglas finas las aplica el modelo (rules.py)."""

    plate = serializers.CharField(max_length=20, allow_blank=True, required=False, default="")
    vin = serializers.CharField(max_length=30, allow_blank=True, required=False, default="")
    brand = serializers.CharField(max_length=60, allow_blank=True)
    model = serializers.CharField(max_length=80, allow_blank=True, required=False, default="")
    year = serializers.IntegerField(required=False, allow_null=True, default=None)
    displacement_cc = serializers.IntegerField(min_value=1, max_value=5000, required=False, allow_null=True, default=None)
    color = serializers.CharField(max_length=40, allow_blank=True, required=False, default="")
    notes = serializers.CharField(allow_blank=True, required=False, default="")


class NewCustomerSerializer(CustomerSerializer):
    """Un cliente nuevo desde el taller: como en la caja, pero con teléfono (regla 2)."""

    def validate_phone(self, value):
        if not value:  # el campo ya recorta los espacios
            raise serializers.ValidationError("El teléfono es obligatorio para avisar cuando la moto esté lista.")
        return value

    def validate(self, attrs):
        if "phone" not in attrs:
            raise serializers.ValidationError({"phone": "El teléfono es obligatorio para avisar cuando la moto esté lista."})
        return super().validate(attrs)


class OwnerChoiceSerializer(serializers.Serializer):
    """Un cliente que ya existe (`owner`) o uno nuevo (`customer`), uno de los dos."""

    owner = serializers.PrimaryKeyRelatedField(queryset=Customer.objects.all(), required=False)
    customer = NewCustomerSerializer(required=False)

    def validate(self, attrs):
        if ("owner" in attrs) == ("customer" in attrs):
            raise serializers.ValidationError({"owner": "Elige un cliente registrado o escribe los datos de uno nuevo."})
        return attrs

    def resolve(self):
        """El dueño elegido; si es nuevo, lo crea (llamar dentro de la transacción)."""
        if "owner" in self.validated_data:
            return self.validated_data["owner"]
        return Customer.objects.create(**self.validated_data["customer"])


class RegisterSerializer(DataSerializer, OwnerChoiceSerializer):
    mileage = serializers.IntegerField(required=False, default=0)  # negativo: lo rechaza el modelo


class UpdateSerializer(DataSerializer):
    is_active = serializers.BooleanField(required=False)


class MileageSerializer(serializers.Serializer):
    mileage = serializers.IntegerField()  # negativo: lo rechaza services.update_mileage
    note = serializers.CharField(max_length=200, allow_blank=True, required=False, default="")


def motorcycles():
    return Motorcycle.objects.select_related("owner").prefetch_related(
        Prefetch("ownerships", queryset=Ownership.objects.select_related("customer")),
        Prefetch("mileage_readings", queryset=MileageReading.objects.select_related("recorded_by")),
    )


def detail(pk, status_code=status.HTTP_200_OK):
    return Response(MotorcycleDetailSerializer(motorcycles().get(pk=pk)).data, status=status_code)


def _call(fn, **kwargs):
    """Un error de las reglas (Django) como error 400 de la API, por campo si lo trae."""
    try:
        return fn(**kwargs)
    except DjangoValidationError as exc:
        raise ValidationError(exc.message_dict if hasattr(exc, "error_dict") else exc.messages)


def search(q):
    """Por placa o chasis (empieza por), documento del dueño (empieza por), teléfono (contiene) o nombre (contiene)."""
    rows = Motorcycle.objects.select_related("owner").annotate(phone_digits=phone_digits("owner__phone"))
    code = normalize_code(q)
    match = Q(owner__name__icontains=q)
    if code:
        match |= Q(plate__startswith=code) | Q(vin__startswith=code)
    digits = only_digits(q)
    if digits:
        match |= number_or_phone(digits, prefix="owner__")
    return rows.filter(match)


class MotorcycleListView(APIView):
    """Busca motos (?q=; activas, o todas con ?inactive=1; máximo 20) o registra una con su dueño."""

    permission_classes = CAN_RECEIVE

    def get(self, request):
        q = request.query_params.get("q", "").strip()
        rows = search(q) if q else Motorcycle.objects.select_related("owner")
        if request.query_params.get("inactive") != "1":
            rows = rows.filter(is_active=True)
        return Response(MotorcycleSerializer(rows.order_by("-updated_at", "-id")[:20], many=True).data)

    def post(self, request):
        data = RegisterSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        fields = {k: v for k, v in data.validated_data.items() if k not in ("owner", "customer")}
        with transaction.atomic():  # si la moto no pasa, el cliente nuevo tampoco queda
            owner = data.resolve()
            moto = _call(services.register_motorcycle, user=request.user, owner=owner, **fields)
        return detail(moto.pk, status.HTTP_201_CREATED)


class MotorcycleDetailView(APIView):
    """Ver la ficha (dueño, dueños anteriores, lecturas) o corregir sus datos. Dueño y kilometraje van aparte."""

    permission_classes = CAN_RECEIVE

    def get(self, request, pk):
        get_object_or_404(Motorcycle, pk=pk)
        return detail(pk)

    def patch(self, request, pk):
        moto = get_object_or_404(Motorcycle, pk=pk)
        data = UpdateSerializer(data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        for field, value in data.validated_data.items():
            setattr(moto, field, value)
        _call(moto.full_clean)
        moto.save()
        return detail(pk)


class MileageView(APIView):
    """Nueva lectura del kilometraje; para bajarlo hace falta `note`."""

    permission_classes = CAN_RECEIVE

    def post(self, request, pk):
        moto = get_object_or_404(Motorcycle, pk=pk)
        data = MileageSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        _call(services.update_mileage, motorcycle=moto, user=request.user, **data.validated_data)
        return detail(pk)


class OwnerView(APIView):
    """Pasa la moto a otro cliente, registrado (`owner`) o nuevo (`customer`). El anterior queda en el historial."""

    permission_classes = CAN_RECEIVE

    def post(self, request, pk):
        moto = get_object_or_404(Motorcycle, pk=pk)
        data = OwnerChoiceSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        _call(services.change_owner, motorcycle=moto, new_owner=data.resolve(), user=request.user)
        return detail(pk)
