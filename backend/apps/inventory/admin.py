from django.contrib import admin

from .models import StockLevel, StockMovement, Warehouse

admin.site.register(Warehouse)


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
