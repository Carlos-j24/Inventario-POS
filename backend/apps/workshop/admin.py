from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import (
    MaintenanceNotice, MaintenancePlan, MaintenanceReminder, MileageReading, Motorcycle, Ownership, WorkOrder, WorkOrderApproval,
    WorkOrderEvent, WorkOrderLine,
)
from .services import check_owner


class OwnershipInline(admin.TabularInline):
    model = Ownership
    fields = readonly_fields = ("customer", "started_at", "ended_at", "created_by")
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False  # el dueño se cambia desde la app (services.change_owner), que cierra el anterior


class MileageInline(admin.TabularInline):
    model = MileageReading
    fields = readonly_fields = ("mileage", "previous", "note", "recorded_at", "recorded_by")
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class MotorcycleForm(forms.ModelForm):
    class Meta:
        model = Motorcycle
        fields = "__all__"

    def clean_owner(self):
        owner = self.cleaned_data["owner"]
        if not self.instance.pk:  # al cambiarlo después está bloqueado (readonly)
            try:
                check_owner(owner)
            except ValidationError as error:
                raise ValidationError(error.messages) from None  # el formulario la pone en este campo
        return owner


@admin.register(Motorcycle)
class MotorcycleAdmin(admin.ModelAdmin):
    form = MotorcycleForm
    list_display = ("plate", "vin", "brand", "model", "owner", "mileage", "is_active")
    list_filter = ("is_active", "brand")
    search_fields = ("plate", "vin", "brand", "model", "owner__name", "owner__id_number", "owner__phone")
    inlines = [OwnershipInline, MileageInline]

    def get_readonly_fields(self, request, obj=None):
        # El dueño y el kilometraje tienen su historia: solo cambian desde la app.
        return ("owner", "mileage", "mileage_at", "created_at", "updated_at") if obj else ("mileage_at",)

    def has_delete_permission(self, request, obj=None):
        return False  # tendrá órdenes e historial: se desactiva, no se borra

    def save_model(self, request, obj, form, change):
        now = timezone.now()
        if not change and obj.mileage:
            obj.mileage_at = now
        super().save_model(request, obj, form, change)
        if not change:  # lo mismo que services.register_motorcycle
            Ownership.objects.create(motorcycle=obj, customer=obj.owner, started_at=now, created_by=request.user)
            if obj.mileage:
                MileageReading.objects.create(motorcycle=obj, mileage=obj.mileage, recorded_at=now, recorded_by=request.user)


# --- Órdenes de trabajo (spec 011): solo para consultar; todo cambio pasa por la app ------------

class ReadOnlyInline(admin.TabularInline):
    # La orden es de solo lectura, así que sus líneas también: el admin no deja agregar ni cambiar.
    extra = 0
    can_delete = False


class WorkOrderLineInline(ReadOnlyInline):
    model = WorkOrderLine
    fields = ("product", "quantity", "unit_price", "approved", "movement", "returned_movement", "added_by")


class WorkOrderApprovalInline(ReadOnlyInline):
    model = WorkOrderApproval
    fields = ("approved_by", "channel", "total", "recorded_by", "recorded_at")
    readonly_fields = ("recorded_at",)


class WorkOrderEventInline(ReadOnlyInline):
    model = WorkOrderEvent
    fields = ("status", "note", "user", "at")
    readonly_fields = ("at",)


@admin.register(WorkOrder)
class WorkOrderAdmin(admin.ModelAdmin):
    list_display = ("number", "motorcycle", "customer", "status", "mechanic", "received_at")
    list_filter = ("status", "mechanic")
    search_fields = ("motorcycle__plate", "motorcycle__vin", "customer__name", "customer__id_number")
    inlines = [WorkOrderLineInline, WorkOrderApprovalInline, WorkOrderEventInline]

    def has_add_permission(self, request):
        return False  # se reciben desde la app (recepción), que actualiza el kilometraje de la moto

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# --- Mantenimientos (spec 012): los planes son configuración; los recordatorios los llevan los servicios --

@admin.register(MaintenancePlan)
class MaintenancePlanAdmin(admin.ModelAdmin):
    list_display = ("name", "every_km", "every_days", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)
    filter_horizontal = ("products",)

    def has_delete_permission(self, request, obj=None):
        return False  # tiene recordatorios: se desactiva, no se borra


class MaintenanceNoticeInline(ReadOnlyInline):
    model = MaintenanceNotice
    fields = ("channel", "user", "at")
    readonly_fields = ("at",)


@admin.register(MaintenanceReminder)
class MaintenanceReminderAdmin(admin.ModelAdmin):
    list_display = ("motorcycle", "plan", "due_date", "due_mileage", "status")
    list_filter = ("status", "plan")
    search_fields = ("motorcycle__plate", "motorcycle__vin", "motorcycle__owner__name")
    inlines = [MaintenanceNoticeInline]

    def has_add_permission(self, request):
        return False  # se crean al entregar una orden

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
