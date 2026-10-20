from django.contrib import admin

from .models import Order, OrderLine, Quote, QuoteLine, Sale, SaleLine, SaleReturn, SaleReturnLine


class ReadOnlyAdmin(admin.ModelAdmin):
    """Solo lectura: ventas y devoluciones se crean y anulan con sus flujos, no se editan."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class SaleLineInline(admin.TabularInline):
    model = SaleLine
    extra = 0
    can_delete = False
    readonly_fields = [f.name for f in SaleLine._meta.fields]


@admin.register(Sale)
class SaleAdmin(ReadOnlyAdmin):
    # Quién vendió (salesperson) y quién cobró (seller) a la vista: spec 002.
    list_display = (
        "number", "occurred_at", "salesperson", "seller", "order_code", "total", "status", "offline", "needs_review",
    )
    list_filter = ("status", "offline", "needs_review", "salesperson", "seller")
    list_select_related = ("salesperson", "seller", "order")
    inlines = [SaleLineInline]

    @admin.display(description="pedido")
    def order_code(self, obj):
        order = getattr(obj, "order", None)
        return order.code if order else "—"


class SaleReturnLineInline(admin.TabularInline):
    model = SaleReturnLine
    extra = 0
    can_delete = False
    readonly_fields = [f.name for f in SaleReturnLine._meta.fields]


@admin.register(SaleReturn)
class SaleReturnAdmin(ReadOnlyAdmin):
    list_display = ("number", "sale", "created_at", "user", "total", "reason")
    inlines = [SaleReturnLineInline]


class OrderLineInline(admin.TabularInline):
    model = OrderLine
    extra = 0
    can_delete = False
    readonly_fields = [f.name for f in OrderLine._meta.fields]


@admin.register(Order)
class OrderAdmin(ReadOnlyAdmin):
    """Pedidos (spec 002): se crean, cancelan y cobran desde la app, no desde el admin."""

    list_display = ("code", "business_date", "salesperson", "total", "shown_status", "sale")
    list_filter = ("status", "business_date", "salesperson")
    search_fields = ("code",)
    list_select_related = ("salesperson", "sale")
    inlines = [OrderLineInline]

    @admin.display(description="estado")
    def shown_status(self, obj):
        return Order.Status(obj.effective_status()).label  # un pendiente de ayer sale como vencido


class QuoteLineInline(admin.TabularInline):
    model = QuoteLine
    extra = 0
    can_delete = False
    readonly_fields = [f.name for f in QuoteLine._meta.fields]


@admin.register(Quote)
class QuoteAdmin(ReadOnlyAdmin):
    """Cotizaciones (spec 007): se crean, anulan y convierten desde la app, no desde el admin."""

    list_display = ("__str__", "created_at", "valid_until", "created_by", "total", "shown_status")
    list_filter = ("status", "created_by")
    search_fields = ("customer_name", "customer_phone", "customer__name")
    list_select_related = ("created_by", "customer")
    inlines = [QuoteLineInline]

    @admin.display(description="estado")
    def shown_status(self, obj):
        return Quote.Status(obj.effective_status()).label  # una vigente con la fecha pasada sale como vencida
