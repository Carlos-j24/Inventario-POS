from django.contrib.auth.models import AbstractUser
from django.db import models


class Permission(models.Model):
    code = models.CharField(max_length=60, unique=True)
    description = models.CharField(max_length=200)

    class Meta:
        ordering = ["code"]
        verbose_name = "permiso"

    def __str__(self):
        return self.code


class Role(models.Model):
    name = models.CharField(max_length=60, unique=True)
    permissions = models.ManyToManyField(Permission, related_name="roles", blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "rol"
        verbose_name_plural = "roles"

    def __str__(self):
        return self.name


class User(AbstractUser):
    roles = models.ManyToManyField(Role, related_name="users", blank=True)

    def permission_codes(self):
        if not self.is_active:
            return set()
        if self.is_superuser:
            return set(Permission.objects.values_list("code", flat=True))
        return set(
            Permission.objects.filter(roles__users=self).values_list("code", flat=True).distinct()
        )

    def has_app_permission(self, code):
        return code in self.permission_codes()
