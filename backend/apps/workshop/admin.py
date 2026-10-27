from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import MileageReading, Motorcycle, Ownership
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
