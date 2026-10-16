from rest_framework import serializers

from apps.cash.models import Payment, Shift
from apps.catalog.models import MONEY, QTY, Product, Unit

from .models import Sale, SaleLine


class SaleLineInputSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.filter(is_active=True))
    quantity = serializers.DecimalField(**QTY)
    unit = serializers.SlugRelatedField(
        slug_field="code", queryset=Unit.objects.all(), required=False, allow_null=True
    )
    unit_price = serializers.DecimalField(**MONEY, min_value=0, required=False, allow_null=True)


class PaymentInputSerializer(serializers.Serializer):
    method = serializers.ChoiceField(choices=Payment.Method.choices)
    amount = serializers.DecimalField(**MONEY)
    reference = serializers.CharField(max_length=60, required=False, allow_blank=True)


class SaleInputSerializer(serializers.Serializer):
    client_uuid = serializers.UUIDField()
    shift = serializers.PrimaryKeyRelatedField(queryset=Shift.objects.all())
    offline = serializers.BooleanField(default=False)
    occurred_at = serializers.DateTimeField(required=False, allow_null=True)
    lines = SaleLineInputSerializer(many=True, allow_empty=False)
    payments = PaymentInputSerializer(many=True, allow_empty=False)

    def validate(self, data):
        if data["offline"]:
            if any(line.get("unit_price") is None for line in data["lines"]):
                raise serializers.ValidationError("Una venta sin conexión debe traer el precio cobrado en cada línea.")
        return data


class SaleLineSerializer(serializers.ModelSerializer):
    product = serializers.SlugRelatedField(slug_field="sku", read_only=True)
    unit = serializers.SlugRelatedField(slug_field="code", read_only=True)

    class Meta:
        model = SaleLine
        fields = [
            "product", "unit", "quantity", "unit_price", "catalog_price",
            "tax_rate", "subtotal", "tax", "total",
        ]


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ["method", "amount", "received", "change", "reference"]


class SaleSerializer(serializers.ModelSerializer):
    warehouse = serializers.SlugRelatedField(slug_field="code", read_only=True)
    seller = serializers.SlugRelatedField(slug_field="username", read_only=True)
    lines = SaleLineSerializer(many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)

    class Meta:
        model = Sale
        fields = [
            "id", "number", "client_uuid", "status", "shift", "warehouse", "seller", "offline",
            "needs_review", "subtotal", "tax", "total", "occurred_at", "created_at", "lines", "payments",
        ]
