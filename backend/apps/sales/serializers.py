from rest_framework import serializers

from apps.catalog.models import MONEY, QTY, Product, Unit
from apps.inventory.models import Warehouse

from .models import Sale, SaleLine


class SaleLineInputSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.filter(is_active=True))
    quantity = serializers.DecimalField(**QTY)
    unit = serializers.SlugRelatedField(
        slug_field="code", queryset=Unit.objects.all(), required=False, allow_null=True
    )
    unit_price = serializers.DecimalField(**MONEY, min_value=0, required=False, allow_null=True)


class SaleInputSerializer(serializers.Serializer):
    client_uuid = serializers.UUIDField()
    warehouse = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.filter(is_active=True))
    offline = serializers.BooleanField(default=False)
    occurred_at = serializers.DateTimeField(required=False, allow_null=True)
    lines = SaleLineInputSerializer(many=True, allow_empty=False)

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


class SaleSerializer(serializers.ModelSerializer):
    warehouse = serializers.SlugRelatedField(slug_field="code", read_only=True)
    seller = serializers.SlugRelatedField(slug_field="username", read_only=True)
    lines = SaleLineSerializer(many=True, read_only=True)

    class Meta:
        model = Sale
        fields = [
            "id", "number", "client_uuid", "status", "warehouse", "seller", "offline",
            "needs_review", "subtotal", "tax", "total", "occurred_at", "created_at", "lines",
        ]
