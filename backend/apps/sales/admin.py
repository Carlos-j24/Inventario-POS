from django.contrib import admin

from .models import Sale, SaleLine, SaleReturn, SaleReturnLine


class ReadOnlyAdmin(admin.ModelAdmin):
    """Solo lectura: ventas y devoluciones se crean y anulan con sus flujos, no se editan."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class SaleLineInline(admin.TabularInline):
    model = SaleLine
    extra = 0
    can_delete = False
    readonly_fields = [f.name for f in SaleLine._meta.fields]


@admin.register(Sale)
class SaleAdmin(ReadOnlyAdmin):
    list_display = ("number", "occurred_at", "seller", "total", "status", "offline", "needs_review")
    list_filter = ("status", "offline", "needs_review")
    inlines = [SaleLineInline]


class SaleReturnLineInline(admin.TabularInline):
    model = SaleReturnLine
    extra = 0
    can_delete = False
    readonly_fields = [f.name for f in SaleReturnLine._meta.fields]


@admin.register(SaleReturn)
class SaleReturnAdmin(ReadOnlyAdmin):
    list_display = ("number", "sale", "created_at", "user", "total", "reason")
    inlines = [SaleReturnLineInline]
