from decimal import Decimal

from rest_framework import serializers

from apps.cash.models import Payment, Shift
from apps.catalog.models import MONEY, QTY, Product, Unit
from apps.customers.models import Customer
from apps.invoicing.models import FiscalDocument

from .models import Order, OrderLine, Sale, SaleLine, SaleReturn, SaleReturnLine


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


class OrderLineChargeSerializer(serializers.Serializer):
    order_line = serializers.PrimaryKeyRelatedField(queryset=OrderLine.objects.all())
    quantity = serializers.DecimalField(**QTY)


class SaleInputSerializer(serializers.Serializer):
    """Venta directa (lines) o cobro de un pedido (order y, si no se cobra completo, order_lines)."""

    client_uuid = serializers.UUIDField()
    shift = serializers.PrimaryKeyRelatedField(queryset=Shift.objects.all())
    offline = serializers.BooleanField(default=False)
    occurred_at = serializers.DateTimeField(required=False, allow_null=True)
    lines = SaleLineInputSerializer(many=True, required=False)
    order = serializers.PrimaryKeyRelatedField(queryset=Order.objects.all(), required=False, allow_null=True)
    order_lines = OrderLineChargeSerializer(many=True, required=False, allow_null=True)
    payments = PaymentInputSerializer(many=True, allow_empty=False)
    # Spec 005: a quién va el documento electrónico (consumidor final si no se dice) y si pidió factura.
    customer = serializers.PrimaryKeyRelatedField(queryset=Customer.objects.filter(is_active=True), required=False, allow_null=True)
    invoice = serializers.BooleanField(default=False)
    contingency_number = serializers.IntegerField(required=False, allow_null=True, min_value=1)

    def validate(self, data):
        order = data.get("order")
        if order is None:
            if not data.get("lines"):
                raise serializers.ValidationError("La venta necesita líneas o un pedido.")
            if data.get("order_lines"):
                raise serializers.ValidationError("order_lines solo va con un pedido.")
        elif data.get("lines"):
            raise serializers.ValidationError("Al cobrar un pedido las líneas salen del pedido: usa order_lines.")
        if data["offline"] and order is None:
            if any(line.get("unit_price") is None for line in data["lines"]):
                raise serializers.ValidationError("Una venta sin conexión debe traer el precio cobrado en cada línea.")
        # Para el servicio: con pedido, lines son las líneas del pedido a cobrar (None = completo).
        order_lines = data.pop("order_lines", None)
        if order is not None:
            data["lines"] = order_lines
        return data


class SaleLineSerializer(serializers.ModelSerializer):
    product = serializers.SlugRelatedField(slug_field="sku", read_only=True)
    unit = serializers.SlugRelatedField(slug_field="code", read_only=True)

    class Meta:
        model = SaleLine
        fields = [
            "id", "product", "unit", "quantity", "unit_price", "catalog_price",
            "tax_rate", "vat_excluded", "subtotal", "tax", "total",
        ]


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ["method", "amount", "received", "change", "reference"]


class SaleSerializer(serializers.ModelSerializer):
    warehouse = serializers.SlugRelatedField(slug_field="code", read_only=True)
    seller = serializers.SlugRelatedField(slug_field="username", read_only=True)
    salesperson = serializers.SlugRelatedField(slug_field="username", read_only=True)
    order_code = serializers.SerializerMethodField()
    lines = SaleLineSerializer(many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)

    class Meta:
        model = Sale
        fields = [
            "id", "number", "client_uuid", "status", "shift", "warehouse", "seller", "salesperson",
            "order_code", "offline", "needs_review", "subtotal", "tax", "total", "occurred_at", "created_at",
            "void_reason", "voided_at", "lines", "payments",
        ]

    def get_order_code(self, obj):
        order = getattr(obj, "order", None)
        return order.code if order else None


class ReviewItemSerializer(SaleSerializer):
    """Venta pendiente de revisión, con las razones a la vista para quien la atiende."""

    reasons = serializers.SerializerMethodField()

    class Meta(SaleSerializer.Meta):
        fields = SaleSerializer.Meta.fields + ["reasons"]

    def get_reasons(self, obj):
        reasons = []
        if any(line.unit_price != line.catalog_price for line in obj.lines.all()):
            reasons.append("Precio distinto al del catálogo")
        if any(line.movement.balance_after < 0 for line in obj.lines.all()):
            reasons.append("Dejó stock negativo")
        if obj.shift.closed_at and obj.created_at > obj.shift.closed_at:
            reasons.append("Llegó con el turno cerrado")
        return reasons


class ReviewSerializer(serializers.Serializer):
    note = serializers.CharField(max_length=200, required=False, allow_blank=True)


class VoidSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=200)


class ReturnLineInputSerializer(serializers.Serializer):
    line = serializers.PrimaryKeyRelatedField(queryset=SaleLine.objects.all(), source="sale_line")
    quantity = serializers.DecimalField(**QTY)


class ReturnInputSerializer(serializers.Serializer):
    client_uuid = serializers.UUIDField()
    shift = serializers.PrimaryKeyRelatedField(queryset=Shift.objects.all())
    refund_method = serializers.ChoiceField(choices=Payment.Method.choices)
    reason = serializers.CharField(max_length=200)
    lines = ReturnLineInputSerializer(many=True, allow_empty=False)


class SaleReturnLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = SaleReturnLine
        fields = ["sale_line", "quantity", "subtotal", "tax", "total"]


class SaleReturnSerializer(serializers.ModelSerializer):
    sale = serializers.SlugRelatedField(slug_field="pk", read_only=True)
    user = serializers.SlugRelatedField(slug_field="username", read_only=True)
    refund_method = serializers.CharField(source="refund.method", read_only=True)
    lines = SaleReturnLineSerializer(many=True, read_only=True)

    class Meta:
        model = SaleReturn
        fields = [
            "id", "number", "client_uuid", "sale", "shift", "user", "reason",
            "total", "refund_method", "created_at", "lines",
        ]


# --- Pedidos (spec 002) -------------------------------------------------------

class OrderLineInputSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.filter(is_active=True))
    quantity = serializers.DecimalField(**QTY)
    unit = serializers.SlugRelatedField(
        slug_field="code", queryset=Unit.objects.all(), required=False, allow_null=True
    )


class OrderInputSerializer(serializers.Serializer):
    client_uuid = serializers.UUIDField()
    lines = OrderLineInputSerializer(many=True, allow_empty=False)


class OrderLineSerializer(serializers.ModelSerializer):
    product = serializers.PrimaryKeyRelatedField(read_only=True)
    sku = serializers.CharField(source="product.sku", read_only=True)
    name = serializers.CharField(source="product.name", read_only=True)
    unit = serializers.SlugRelatedField(slug_field="code", read_only=True)

    class Meta:
        model = OrderLine
        fields = ["id", "product", "sku", "name", "unit", "quantity", "unit_price", "total"]


class OrderSerializer(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()
    salesperson = serializers.SlugRelatedField(slug_field="username", read_only=True)
    sale_number = serializers.SerializerMethodField()
    lines = OrderLineSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = [
            "id", "code", "business_date", "client_uuid", "status", "salesperson", "total",
            "created_at", "sale_number", "lines",
        ]

    def get_status(self, obj):
        return obj.effective_status()  # un pendiente de ayer se muestra vencido

    def get_sale_number(self, obj):
        return obj.sale.number if obj.sale_id else None


# --- Supervisor (spec 003) ------------------------------------------------------

class SaleListSerializer(serializers.ModelSerializer):
    """Fila de la lista de ventas: lo justo para encontrar la venta."""

    register = serializers.CharField(source="shift.register.code", read_only=True)
    seller = serializers.SlugRelatedField(slug_field="username", read_only=True)
    salesperson = serializers.SlugRelatedField(slug_field="username", read_only=True)
    order_code = serializers.SerializerMethodField()

    class Meta:
        model = Sale
        fields = [
            "id", "number", "occurred_at", "register", "seller", "salesperson", "order_code",
            "total", "status", "offline", "needs_review",
        ]

    def get_order_code(self, obj):
        order = getattr(obj, "order", None)
        return order.code if order else None


class SaleDetailLineSerializer(SaleLineSerializer):
    name = serializers.CharField(source="product.name", read_only=True)
    returned_quantity = serializers.SerializerMethodField()

    class Meta(SaleLineSerializer.Meta):
        fields = SaleLineSerializer.Meta.fields + ["name", "returned_quantity"]

    def get_returned_quantity(self, obj):
        # Usa el prefetch de return_lines: sin consultas extra por línea.
        return str(sum((r.quantity for r in obj.return_lines.all()), Decimal(0)))


class FiscalDocumentSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    customer = serializers.CharField(source="customer.name", read_only=True)
    corrects = serializers.CharField(source="corrects.code", read_only=True, default=None)

    class Meta:
        model = FiscalDocument
        fields = [
            "id", "kind", "kind_label", "code", "status", "status_label", "customer", "issued_at",
            "subtotal", "tax", "total", "cude", "qr_data", "corrects", "last_error", "contingency",
        ]


class SaleDetailSerializer(SaleSerializer):
    register = serializers.CharField(source="shift.register.code", read_only=True)
    shift_open = serializers.SerializerMethodField()
    lines = SaleDetailLineSerializer(many=True, read_only=True)
    returns = SaleReturnSerializer(many=True, read_only=True)
    fiscal_documents = FiscalDocumentSerializer(many=True, read_only=True)

    class Meta(SaleSerializer.Meta):
        fields = SaleSerializer.Meta.fields + ["register", "shift_open", "returns", "reviewed_at", "review_note", "fiscal_documents"]

    def get_shift_open(self, obj):
        """Anular solo se puede con el turno de la venta abierto: la pantalla lo usa para ofrecer devolución."""
        return obj.shift.status == "OPEN"
