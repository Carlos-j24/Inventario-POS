from django.contrib import admin

from .models import CashRegister, Payment, Shift

admin.site.register(CashRegister)


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    can_delete = False
    fields = ("sale", "method", "amount", "received", "change", "reference")
    readonly_fields = fields


@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    """Solo lectura: los turnos se abren y cierran desde el POS."""

    list_display = ("register", "status", "opened_by", "opened_at", "expected_cash", "counted_cash", "difference")
    list_filter = ("status", "register")
    inlines = [PaymentInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
