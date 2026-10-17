from rest_framework import serializers

from .models import FiscalDocument, FiscalEvent, NumberingResolution
from .numbering import resolution_status
from .queue import alert, deadline


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


class FiscalEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = FiscalEvent
        fields = ["at", "kind", "detail"]


class FiscalDocumentRowSerializer(serializers.ModelSerializer):
    """Fila de la bandeja del supervisor (spec 005, T4)."""

    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    sale_number = serializers.CharField(source="sale.number", read_only=True)
    register = serializers.CharField(source="sale.shift.register.code", read_only=True)
    customer = serializers.CharField(source="customer.name", read_only=True)
    customer_id = serializers.IntegerField(source="customer.id", read_only=True)
    deadline = serializers.SerializerMethodField()
    alert = serializers.SerializerMethodField()
    waiting_for = serializers.SerializerMethodField()

    class Meta:
        model = FiscalDocument
        fields = [
            "id", "kind", "kind_label", "code", "status", "status_label", "sale", "sale_number", "register",
            "customer", "customer_id", "total", "issued_at", "attempts", "last_error", "next_attempt_at",
            "validated_at", "cude", "contingency", "deadline", "alert", "waiting_for",
        ]

    def get_deadline(self, obj):
        return deadline(obj).isoformat()

    def get_alert(self, obj):
        return alert(obj)

    def get_waiting_for(self, obj):
        """Una nota no sale hasta que la DIAN valide el documento que corrige."""
        if obj.corrects and obj.corrects.status != FiscalDocument.Status.VALIDATED and obj.status == FiscalDocument.Status.PENDING:
            return obj.corrects.code
        return None


class FiscalDocumentDetailSerializer(FiscalDocumentRowSerializer):
    events = FiscalEventSerializer(many=True, read_only=True)
    corrects = serializers.CharField(source="corrects.code", read_only=True, default=None)

    class Meta(FiscalDocumentRowSerializer.Meta):
        fields = FiscalDocumentRowSerializer.Meta.fields + ["subtotal", "tax", "qr_data", "corrects", "events"]
