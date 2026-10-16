from django.contrib import admin

from .models import Sale, SaleLine


class SaleLineInline(admin.TabularInline):
    model = SaleLine
    extra = 0
    can_delete = False
    readonly_fields = [f.name for f in SaleLine._meta.fields]


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    """Solo lectura: las ventas se anulan con su flujo, no se editan."""

    list_display = ("number", "occurred_at", "seller", "total", "status", "offline", "needs_review")
    list_filter = ("status", "offline", "needs_review")
    inlines = [SaleLineInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
