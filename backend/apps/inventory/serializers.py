from rest_framework import serializers

from apps.catalog.models import MONEY, QTY, Product, Unit

from .models import StockLevel, StockMovement, Warehouse


class ReceiptSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.filter(is_active=True))
    warehouse = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.filter(is_active=True))
    quantity = serializers.DecimalField(**QTY, min_value=0)
    unit = serializers.SlugRelatedField(
        slug_field="code", queryset=Unit.objects.all(), required=False, allow_null=True
    )
    unit_cost = serializers.DecimalField(**MONEY, min_value=0)
    reference = serializers.CharField(max_length=80, required=False, allow_blank=True)
    client_uuid = serializers.UUIDField(required=False, allow_null=True)


class StockMovementSerializer(serializers.ModelSerializer):
    product = serializers.SlugRelatedField(slug_field="sku", read_only=True)
    warehouse = serializers.SlugRelatedField(slug_field="code", read_only=True)
    user = serializers.SlugRelatedField(slug_field="username", read_only=True)

    class Meta:
        model = StockMovement
        fields = [
            "id", "client_uuid", "kind", "product", "warehouse", "quantity", "unit_cost",
            "balance_after", "reference", "needs_review", "user", "occurred_at", "created_at",
        ]


class StockLevelSerializer(serializers.ModelSerializer):
    product = serializers.SlugRelatedField(slug_field="sku", read_only=True)
    warehouse = serializers.SlugRelatedField(slug_field="code", read_only=True)
    below_min = serializers.SerializerMethodField()

    class Meta:
        model = StockLevel
        fields = ["product", "warehouse", "quantity", "below_min"]

    def get_below_min(self, obj):
        return obj.quantity < obj.product.min_stock
