from django.contrib import admin

from .models import Expense, ExpenseCategory


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active")

    def has_delete_permission(self, request, obj=None):
        return False  # se desactiva: los gastos conservan su categoría


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    """Solo para consultar: los gastos se anotan, corrigen y anulan en la app, que deja el rastro."""

    list_display = ("spent_on", "category", "amount", "status", "shift", "created_by")
    list_filter = ("status", "category")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
