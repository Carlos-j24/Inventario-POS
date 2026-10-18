from django.contrib import admin

from .models import Business, ContingencyBlock, FiscalDocument, FiscalEvent, NumberingResolution
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

    list_display = ("code", "kind", "status", "contingency", "sale", "customer", "total", "issued_at", "attempts")
    list_filter = ("kind", "status", "contingency")
    search_fields = ("number", "cude", "sale__id", "customer__name", "customer__id_number")
    inlines = [FiscalEventInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ContingencyBlock)
class ContingencyBlockAdmin(admin.ModelAdmin):
    list_display = ("register", "resolution", "start", "end", "reserved_by", "reserved_at")
    list_filter = ("register",)

    def has_add_permission(self, request):
        return False  # los reserva el POS

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    """Un solo registro: los datos del vendedor que salen en cada tiquete y documento."""

    readonly_fields = ("check_digit",)

    def has_add_permission(self, request):
        return not Business.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
