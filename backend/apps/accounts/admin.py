from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Permission, Role, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (("Roles", {"fields": ("roles",)}),)
    filter_horizontal = ("roles", "groups", "user_permissions")


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    filter_horizontal = ("permissions",)


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ("code", "description")
