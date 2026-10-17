from django.contrib import admin

from .models import Customer


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "id_type", "id_number", "check_digit", "person_type", "email", "is_active")
    list_filter = ("id_type", "person_type", "is_active")
    search_fields = ("name", "id_number", "email")
    readonly_fields = ("check_digit", "created_at", "updated_at")

    def has_delete_permission(self, request, obj=None):
        return False  # tendrán documentos fiscales: se desactivan, no se borran

    def has_change_permission(self, request, obj=None):
        return not (obj and obj.is_final_consumer) and super().has_change_permission(request, obj)
