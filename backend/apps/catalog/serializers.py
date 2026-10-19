from rest_framework import serializers

from .models import Category, PriceChange, Product, ProductUnit, Unit


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


# --- Administración del catálogo (spec 006, T1) ---------------------------------

class CategorySerializer(serializers.ModelSerializer):
    products = serializers.IntegerField(source="products.count", read_only=True)

    class Meta:
        model = Category
        fields = ["id", "name", "products"]


class UnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = Unit
        fields = ["id", "code", "name"]


class PresentationSerializer(serializers.ModelSerializer):
    unit = serializers.SlugRelatedField(slug_field="code", queryset=Unit.objects.all())
    in_use = serializers.SerializerMethodField()

    class Meta:
        model = ProductUnit
        fields = ["id", "unit", "factor", "barcode", "is_active", "in_use"]
        validators = []  # las reglas van en catalog.services

    def get_in_use(self, obj):
        from .services import unit_in_use

        return unit_in_use(obj)


class ProductAdminSerializer(serializers.ModelSerializer):
    category = serializers.PrimaryKeyRelatedField(queryset=Category.objects.all())
    category_name = serializers.CharField(source="category.name", read_only=True)
    base_unit = serializers.SlugRelatedField(slug_field="code", queryset=Unit.objects.all())
    units = PresentationSerializer(many=True, read_only=True)
    has_movements = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id", "sku", "name", "category", "category_name", "base_unit", "barcode", "sale_price", "tax_rate",
            "vat_excluded", "allows_fractions", "min_stock", "is_active", "price_pending", "has_movements", "units",
        ]
        read_only_fields = ["price_pending"]
        extra_kwargs = {"sale_price": {"required": False}, "barcode": {"required": False, "allow_null": True}}
        validators = []  # unicidad y reglas en catalog.services

    def get_has_movements(self, obj):
        from .services import has_movements

        return has_movements(obj)


class PriceChangeSerializer(serializers.ModelSerializer):
    user = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = PriceChange
        fields = ["old_price", "new_price", "user", "at"]
