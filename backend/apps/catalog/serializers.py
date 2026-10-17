from rest_framework import serializers

from .models import Product, ProductUnit


class ProductUnitSerializer(serializers.ModelSerializer):
    unit = serializers.SlugRelatedField(slug_field="code", read_only=True)

    class Meta:
        model = ProductUnit
        fields = ["unit", "factor", "barcode"]


class ProductSerializer(serializers.ModelSerializer):
    base_unit = serializers.SlugRelatedField(slug_field="code", read_only=True)
    category = serializers.StringRelatedField()
    units = ProductUnitSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = [
            "id", "sku", "name", "category", "base_unit", "barcode",
            "sale_price", "tax_rate", "vat_excluded", "allows_fractions", "min_stock", "units",
        ]
