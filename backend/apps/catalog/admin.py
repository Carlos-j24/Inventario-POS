from django.contrib import admin

from .models import Category, PriceChange, Product, ProductUnit, Unit


class ProductUnitInline(admin.TabularInline):
    model = ProductUnit
    extra = 0


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("sku", "name", "category", "base_unit", "sale_price", "tax_rate", "vat_excluded", "is_active", "price_pending")
    list_filter = ("category", "tax_rate", "vat_excluded", "is_active", "price_pending")
    search_fields = ("sku", "name", "barcode")
    inlines = [ProductUnitInline]

    def get_readonly_fields(self, request, obj=None):
        # El precio se cambia en la app, para que quede en el historial (spec 006).
        return ("sale_price", "price_pending") if obj else ("price_pending",)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change:
            PriceChange.objects.create(product=obj, old_price=None, new_price=obj.sale_price, user=request.user)


@admin.register(PriceChange)
class PriceChangeAdmin(admin.ModelAdmin):
    list_display = ("product", "old_price", "new_price", "user", "at")
    search_fields = ("product__sku", "product__name")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(Category)
admin.site.register(Unit)
