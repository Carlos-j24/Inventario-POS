from rest_framework import serializers

from .models import NumberingResolution
from .numbering import resolution_status


class NumberingResolutionSerializer(serializers.ModelSerializer):
    register = serializers.CharField(source="register.code", read_only=True)
    document_type_label = serializers.CharField(source="get_document_type_display", read_only=True)
    remaining = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    class Meta:
        model = NumberingResolution
        fields = [
            "id", "register", "document_type", "document_type_label", "number", "issued_on", "valid_from",
            "valid_until", "prefix", "range_from", "range_to", "next_number", "remaining", "status",
        ]

    def get_remaining(self, obj):
        return resolution_status(obj)["remaining"]

    def get_status(self, obj):
        return resolution_status(obj)
