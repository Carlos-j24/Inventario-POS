"""API de cotizaciones (spec 007, T3).

Quién ve qué: la lista muestra las propias, y todas a quien tiene sales.void o reports.view. Con el
número exacto (COT-000045 o 45) cualquier vendedor la encuentra, porque el cliente puede volver y lo
atiende otro: por eso el detalle, duplicar y convertir están abiertos a quien tiene sales.create.
Anular una ajena exige sales.void o reports.view (lo revisa el servicio).
"""
from collections import defaultdict
from decimal import Decimal

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.drf import require, require_any
from apps.catalog.models import QTY, Product, Unit
from apps.customers.models import Customer
from apps.invoicing.ticket import business_data

from . import quotes as service
from .models import Order, OrderLine, Quote, QuoteLine
from .orders import stock_warnings
from .serializers import OrderSerializer
from .services import split_tax

LIST_LIMIT = 200
CAN_QUOTE = require("sales.create")
CAN_SEE = require_any("sales.create", *service.MANAGERS)


def _money(value):
    return str(Decimal(value).quantize(Decimal("0.01")))


# --- entrada -----------------------------------------------------------------------

class QuoteLineInputSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())  # el servicio explica si no está a la venta
    unit = serializers.SlugRelatedField(slug_field="code", queryset=Unit.objects.all(), required=False, allow_null=True)
    quantity = serializers.DecimalField(**QTY)


class QuoteInputSerializer(serializers.Serializer):
    client_uuid = serializers.UUIDField()
    customer = serializers.PrimaryKeyRelatedField(queryset=Customer.objects.all(), required=False, allow_null=True)
    customer_name = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    customer_phone = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")
    note = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")
    valid_days = serializers.IntegerField(required=False, default=service.DEFAULT_VALID_DAYS)
    lines = QuoteLineInputSerializer(many=True, allow_empty=False)


class DuplicateInputSerializer(serializers.Serializer):
    client_uuid = serializers.UUIDField()
    valid_days = serializers.IntegerField(required=False, default=service.DEFAULT_VALID_DAYS)


class ConvertLineSerializer(serializers.Serializer):
    quote_line = serializers.IntegerField()
    quantity = serializers.DecimalField(**QTY)


class ConvertInputSerializer(serializers.Serializer):
    client_uuid = serializers.UUIDField()
    lines = ConvertLineSerializer(many=True, required=False, allow_null=True, default=None)  # sin líneas: todo lo que queda


# --- salida ------------------------------------------------------------------------

class QuoteRowSerializer(serializers.ModelSerializer):
    """Fila de la lista: lo justo para encontrarla."""

    number = serializers.CharField(read_only=True)
    customer = serializers.CharField(source="customer_label", read_only=True)
    status = serializers.SerializerMethodField()
    status_label = serializers.SerializerMethodField()
    created_by = serializers.SlugRelatedField(slug_field="username", read_only=True)
    lines_count = serializers.IntegerField(source="lines.count", read_only=True)

    class Meta:
        model = Quote
        fields = [
            "id", "number", "customer", "customer_phone", "status", "status_label", "valid_until", "total",
            "created_by", "created_at", "lines_count",
        ]

    def get_status(self, quote):
        return quote.effective_status()

    def get_status_label(self, quote):
        return Quote.Status(quote.effective_status()).label


def _line_data(line):
    pending, charged = service.in_orders(line)
    subtotal, tax = split_tax(line.total, Decimal(line.tax_rate))
    return {
        "id": line.pk, "product": line.product_id, "sku": line.product.sku, "name": line.product.name,
        "unit": line.unit.code, "quantity": str(line.quantity), "unit_price": _money(line.unit_price),
        "tax_rate": line.tax_rate, "vat_excluded": line.vat_excluded, "total": _money(line.total),
        "subtotal": _money(subtotal), "tax": _money(tax), "active": line.product.is_active,
        # Siempre con 3 decimales, como las cantidades: sin pedidos, la suma es un 0 sin escala.
        "in_orders": f"{pending:.3f}", "charged": f"{charged:.3f}", "remaining": f"{max(line.quantity - pending - charged, Decimal(0)):.3f}",
    }


def detail(quote):
    """Todo lo de la cotización: para la pantalla y para imprimirla (los datos del negocio y el IVA por tarifa)."""
    lines = [_line_data(line) for line in quote.lines.all()]
    taxes = defaultdict(lambda: {"base": Decimal(0), "tax": Decimal(0)})
    for line in lines:
        key = "excluido" if line["vat_excluded"] else line["tax_rate"]
        taxes[key]["base"] += Decimal(line["subtotal"])
        taxes[key]["tax"] += Decimal(line["tax"])
    status_ = quote.effective_status()
    orders = Order.objects.filter(lines__quote_line__quote=quote).distinct().select_related("sale").order_by("created_at")
    customer = quote.customer
    return {
        **QuoteRowSerializer(quote).data,
        "customer_id": quote.customer_id,
        "customer_document": (
            f"{customer.get_id_type_display()} {customer.id_number}" + (f"-{customer.check_digit}" if customer.check_digit else "")
        ) if customer else None,
        "note": quote.note,
        "void_note": quote.void_note,
        "voided_by": quote.voided_by.username if quote.voided_by_id else None,
        "duplicated_from": quote.duplicated_from.number if quote.duplicated_from_id else None,
        "lines": lines,
        "subtotal": _money(sum((Decimal(l["subtotal"]) for l in lines), Decimal(0))),
        "tax": _money(sum((Decimal(l["tax"]) for l in lines), Decimal(0))),
        "taxes": [{"rate": rate, "base": _money(v["base"]), "tax": _money(v["tax"])} for rate, v in sorted(taxes.items())],
        "orders": [
            {"id": o.pk, "code": o.code, "status": o.effective_status(), "total": _money(o.total),
             "sale_number": o.sale.number if o.sale_id else None, "created_at": o.created_at.isoformat()}
            for o in orders
        ],
        "can_convert": status_ == Quote.Status.VALID,
        "business": business_data(),
    }


def _quotes():
    return Quote.objects.select_related("created_by", "customer", "voided_by", "duplicated_from").prefetch_related(
        Prefetch("lines", queryset=QuoteLine.objects.select_related("product", "unit")),
    )


def _call(fn, **kwargs):
    try:
        return fn(**kwargs)
    except DjangoPermissionDenied as exc:
        raise PermissionDenied(str(exc))
    except DjangoValidationError as exc:
        raise ValidationError(exc.messages)


def _is_number(text):
    digits = (text or "").strip().upper().removeprefix("COT-").lstrip("0")
    return digits.isdigit()


# --- vistas ------------------------------------------------------------------------

class QuoteListView(APIView):
    """GET: ?q= (número, nombre o teléfono), ?status=VALID|EXPIRED|CONVERTED|VOIDED (vacío: todas), ?mine=1.
    Las más recientes primero, máximo 200. POST: crear."""

    def get_permissions(self):
        return [CAN_QUOTE()] if self.request.method == "POST" else [CAN_SEE()]

    def get(self, request):
        text = request.query_params.get("q", "")
        rows = service.search(_quotes(), text)
        wanted = request.query_params.get("status", Quote.Status.VALID)
        rows = service.filter_status(rows, wanted)
        sees_all = service.can_manage(request.user) and request.query_params.get("mine") != "1"
        if not sees_all and not _is_number(text):
            rows = rows.filter(created_by=request.user)  # con el número exacto se encuentra la de otro vendedor
        return Response(QuoteRowSerializer(rows[:LIST_LIMIT], many=True).data)

    def post(self, request):
        data = QuoteInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        quote, created = _call(service.create_quote, user=request.user, **data.validated_data)
        return Response(detail(_quotes().get(pk=quote.pk)), status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class QuoteDetailView(APIView):
    permission_classes = [CAN_SEE]

    def get(self, request, pk):
        return Response(detail(get_object_or_404(_quotes(), pk=pk)))


class QuoteVoidView(APIView):
    permission_classes = [CAN_SEE]

    def post(self, request, pk):
        quote = _call(service.void_quote, quote=get_object_or_404(Quote, pk=pk), user=request.user, note=request.data.get("note", ""))
        return Response(detail(_quotes().get(pk=quote.pk)))


class QuoteDuplicateView(APIView):
    permission_classes = [CAN_QUOTE]

    def post(self, request, pk):
        data = DuplicateInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        quote, created, skipped = _call(
            service.duplicate_quote, quote=get_object_or_404(Quote, pk=pk), user=request.user, **data.validated_data,
        )
        body = {**detail(_quotes().get(pk=quote.pk)), "skipped": skipped}
        return Response(body, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class QuoteConvertView(APIView):
    """Convierte en pedido (todo lo que queda o las líneas dadas). Devuelve el pedido, su código y los avisos de stock."""

    permission_classes = [CAN_QUOTE]

    def post(self, request, pk):
        data = ConvertInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        order, created = _call(
            service.convert_quote, quote=get_object_or_404(Quote, pk=pk), user=request.user, **data.validated_data,
        )
        order = Order.objects.select_related("salesperson", "sale").prefetch_related(
            Prefetch("lines", queryset=OrderLine.objects.select_related("product", "unit")),
        ).get(pk=order.pk)
        body = OrderSerializer(order).data
        # Siempre con 3 decimales: SQLite y PostgreSQL devuelven la suma con distinta escala.
        body["warnings"] = [{**w, "available": f"{w['available']:.3f}"} for w in stock_warnings(order)]
        return Response(body, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)
