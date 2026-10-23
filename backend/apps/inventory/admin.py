from django.contrib import admin

from .models import (
    Adjustment, AdjustmentLine, CountLine, PhysicalCount, StockLevel, StockMovement, Transfer, TransferLine, Warehouse,
)


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    """Marcar una como principal desmarca la anterior; una inactiva deja de serlo (Warehouse.save)."""

    list_display = ("code", "name", "is_active", "is_default")
    list_filter = ("is_active",)


@admin.register(StockLevel)
class StockLevelAdmin(admin.ModelAdmin):
    list_display = ("product", "warehouse", "quantity")
    list_filter = ("warehouse",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    """Solo lectura: el kardex no se edita desde el admin."""

    list_display = ("created_at", "kind", "product", "warehouse", "quantity", "balance_after", "user")
    list_filter = ("kind", "warehouse", "needs_review")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class AdjustmentLineInline(admin.TabularInline):
    model = AdjustmentLine
    extra = 0
    can_delete = False
    readonly_fields = ("product", "unit", "quantity", "base_quantity", "unit_cost", "movement")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Adjustment)
class AdjustmentAdmin(admin.ModelAdmin):
    """Solo consulta: los ajustes se piden y aprueban en la app (spec 006)."""

    list_display = ("number", "warehouse", "reason", "status", "requested_by", "decided_by", "created_at")
    list_filter = ("status", "reason", "warehouse")
    inlines = [AdjustmentLineInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class CountLineInline(admin.TabularInline):
    model = CountLine
    extra = 0
    can_delete = False
    readonly_fields = ("product", "counted", "counted_at", "counted_by", "marked_zero", "expected", "difference")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(PhysicalCount)
class PhysicalCountAdmin(admin.ModelAdmin):
    """Solo consulta: los conteos se hacen en la app (spec 006)."""

    list_display = ("number", "warehouse", "category", "status", "opened_by", "decided_by", "created_at")
    list_filter = ("status", "warehouse")
    inlines = [CountLineInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class TransferLineInline(admin.TabularInline):
    model = TransferLine
    extra = 0
    can_delete = False
    readonly_fields = ("product", "unit", "quantity", "base_quantity", "out_movement", "in_movement")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Transfer)
class TransferAdmin(admin.ModelAdmin):
    """Solo consulta: los traslados se hacen en la app (spec 006)."""

    list_display = ("number", "origin", "destination", "created_by", "created_at")
    list_filter = ("origin", "destination")
    inlines = [TransferLineInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
