from django.contrib import admin

from .models import Category, Product, ProductUnit, Unit


class ProductUnitInline(admin.TabularInline):
    model = ProductUnit
    extra = 0


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("sku", "name", "category", "base_unit", "sale_price", "tax_rate", "vat_excluded", "is_active")
    list_filter = ("category", "tax_rate", "vat_excluded", "is_active")
    search_fields = ("sku", "name", "barcode")
    inlines = [ProductUnitInline]


admin.site.register(Category)
admin.site.register(Unit)
