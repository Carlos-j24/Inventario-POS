from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import Permission, Role, User
from .services import ensure_someone_can_manage


def _django_errors(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except DjangoValidationError as exc:
        raise serializers.ValidationError(exc.messages)


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(trim_whitespace=False)


class MeSerializer(serializers.ModelSerializer):
    roles = serializers.SlugRelatedField(slug_field="name", many=True, read_only=True)
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "roles", "permissions"]

    def get_permissions(self, obj):
        return sorted(obj.permission_codes())


class PermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permission
        fields = ["code", "description"]


class RoleSerializer(serializers.ModelSerializer):
    permissions = serializers.SlugRelatedField(
        slug_field="code", many=True, queryset=Permission.objects.all()
    )

    class Meta:
        model = Role
        fields = ["id", "name", "permissions"]

    def update(self, instance, validated_data):
        if "permissions" in validated_data:
            _django_errors(
                ensure_someone_can_manage, role=instance, permissions=validated_data["permissions"]
            )
        return super().update(instance, validated_data)


class UserSerializer(serializers.ModelSerializer):
    roles = serializers.SlugRelatedField(slug_field="name", many=True, queryset=Role.objects.all())
    password = serializers.CharField(write_only=True, required=False, trim_whitespace=False)

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "email", "is_active", "roles", "password", "last_login"]
        read_only_fields = ["last_login"]

    def validate(self, data):
        if self.instance is None and not data.get("password"):
            raise serializers.ValidationError({"password": "Un usuario nuevo necesita contraseña."})
        if data.get("password"):
            candidate = self.instance or User(username=data.get("username", ""))
            _django_errors(validate_password, data["password"], candidate)
        if self.instance is not None:
            request = self.context["request"]
            if self.instance.pk == request.user.pk and data.get("is_active") is False:
                raise serializers.ValidationError("No puedes desactivar tu propio usuario.")
            _django_errors(
                ensure_someone_can_manage,
                user=self.instance,
                active=data.get("is_active", self.instance.is_active),
                roles=data.get("roles"),
            )
        return data

    def create(self, validated_data):
        roles = validated_data.pop("roles", [])
        user = User.objects.create_user(**validated_data)
        user.roles.set(roles)
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        user = super().update(instance, validated_data)
        if password:
            user.set_password(password)
            user.save(update_fields=["password"])
        return user
