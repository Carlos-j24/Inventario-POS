from django.contrib import admin

from .models import FiscalDocument, FiscalEvent, NumberingResolution
from .numbering import resolution_status


@admin.register(NumberingResolution)
class NumberingResolutionAdmin(admin.ModelAdmin):
    list_display = ("register", "document_type", "number", "prefix", "range_from", "range_to", "next_number", "valid_until", "warnings", "is_active")
    list_filter = ("register", "document_type", "is_active")
    search_fields = ("number", "prefix")
    readonly_fields = ("next_number", "created_at")

    @admin.display(description="avisos")
    def warnings(self, obj):
        return " ".join(resolution_status(obj)["warnings"]) or "—"

    def get_readonly_fields(self, request, obj=None):
        # Una vez creada, el rango y el prefijo no se tocan: ya puede haber documentos con esos números.
        fixed = ("register", "document_type", "prefix", "range_from", "range_to") if obj else ()
        return (*self.readonly_fields, *fixed)

    def has_delete_permission(self, request, obj=None):
        return False  # se desactiva; no se borra


class FiscalEventInline(admin.TabularInline):
    model = FiscalEvent
    extra = 0
    can_delete = False
    readonly_fields = ("at", "kind", "detail")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(FiscalDocument)
class FiscalDocumentAdmin(admin.ModelAdmin):
    """Solo lectura: los documentos los crea el sistema y la DIAN los valida."""

    list_display = ("code", "kind", "status", "sale", "customer", "total", "issued_at", "attempts")
    list_filter = ("kind", "status")
    search_fields = ("number", "cude", "sale__id", "customer__name", "customer__id_number")
    inlines = [FiscalEventInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
