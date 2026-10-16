from rest_framework import serializers

from apps.catalog.models import MONEY

from .models import CashRegister, Shift
from .services import shift_summary


class OpenShiftSerializer(serializers.Serializer):
    register = serializers.PrimaryKeyRelatedField(queryset=CashRegister.objects.all())
    opening_float = serializers.DecimalField(**MONEY)


class CloseShiftSerializer(serializers.Serializer):
    counted_cash = serializers.DecimalField(**MONEY)
    notes = serializers.CharField(required=False, allow_blank=True)


class ShiftSerializer(serializers.ModelSerializer):
    register = serializers.SlugRelatedField(slug_field="code", read_only=True)
    opened_by = serializers.SlugRelatedField(slug_field="username", read_only=True)
    closed_by = serializers.SlugRelatedField(slug_field="username", read_only=True)
    summary = serializers.SerializerMethodField()

    class Meta:
        model = Shift
        fields = [
            "id", "register", "status", "opened_by", "opened_at", "opening_float",
            "closed_by", "closed_at", "expected_cash", "counted_cash", "difference", "notes", "summary",
        ]

    def get_summary(self, obj):
        data = shift_summary(obj)
        return {
            "sales": data["sales"],
            "by_method": {k: str(v) for k, v in data["by_method"].items()},
            "refunds": {k: str(v) for k, v in data["refunds"].items()},
            "expected_cash": str(data["expected_cash"]),
        }
