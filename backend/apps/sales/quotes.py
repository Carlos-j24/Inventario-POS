"""Cotizaciones (spec 007): lo que se le cotiza a un cliente, con vigencia.

- Crear: congela el precio del catálogo y la tarifa de IVA en cada línea. Vigencia de 1 a 30 días, 8 por
  defecto (decisión 2); sin descuentos (decisión 3). A nombre de alguien: escrito a mano o un cliente
  registrado. Solo productos activos y una línea por producto y unidad.
- Anular: la propia, o cualquiera con sales.void o reports.view. Solo vigentes.
- Duplicar: una nueva con las mismas cantidades y los precios de hoy (así se "renueva" una vencida).
- Vencida: vigente con la fecha pasada, aunque nadie haya cambiado el estado (como los pedidos de ayer).
- Por convertir: lo cotizado menos lo que va en pedidos pendientes o ya cobrados; lo de un pedido
  cancelado o vencido vuelve a quedar disponible (decisión 4).
- Convertir (T2): una parte o todo lo que queda, en un pedido con el precio cotizado, mientras esté
  vigente. Al cobrarse, la venta no queda para revisión por la diferencia con el catálogo, y la
  cotización queda CONVERTIDA cuando lo cobrado cubre todo lo cotizado.
La cotización no mueve inventario ni reserva existencias.
"""
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q, Sum
from django.utils import timezone

from apps.catalog.units import to_base_quantity

from .models import Order, Quote, QuoteLine, business_date
from .orders import create_order
from .services import catalog_price, money

DEFAULT_VALID_DAYS = 8
MAX_VALID_DAYS = 30
MANAGERS = ("sales.void", "reports.view")  # ven y anulan las cotizaciones de todos


def can_manage(user):
    return any(user.has_app_permission(code) for code in MANAGERS)


def _priced_lines(lines):
    """Valida las líneas y les pone el precio y la tarifa de hoy."""
    if not lines:
        raise ValidationError("La cotización no tiene líneas.")
    seen = set()
    priced = []
    for line in lines:
        product = line["product"]
        unit = line.get("unit") or product.base_unit
        quantity = Decimal(line["quantity"])
        if not product.is_active:
            raise ValidationError(f"{product.sku} no está a la venta: no se puede cotizar.")
        if quantity <= 0:
            raise ValidationError(f"{product.sku}: la cantidad debe ser mayor que cero.")
        if (product.pk, unit.pk) in seen:
            raise ValidationError(f"{product.sku} está dos veces en {unit.code}: junta las cantidades en una línea.")
        seen.add((product.pk, unit.pk))
        to_base_quantity(product, quantity, unit)  # valida la unidad y las fracciones
        price = catalog_price(product, unit)
        priced.append(QuoteLine(
            product=product, unit=unit, quantity=quantity, unit_price=price,
            tax_rate=product.tax_rate, vat_excluded=product.vat_excluded, total=money(price * quantity),
        ))
    return priced


def create_quote(*, user, client_uuid, lines, customer=None, customer_name="", customer_phone="", note="",
                 valid_days=DEFAULT_VALID_DAYS, duplicated_from=None):
    """Crea una cotización vigente. Devuelve (cotización, creada); con el mismo client_uuid, la que ya existe."""
    existing = Quote.objects.filter(client_uuid=client_uuid).first()
    if existing:
        return existing, False
    customer_name = (customer_name or "").strip()
    if not customer_name and customer is None:
        raise ValidationError("Escribe a nombre de quién va la cotización o elige un cliente.")
    if customer is not None and not customer.is_active:
        raise ValidationError("Ese cliente está inactivo.")
    if not 1 <= int(valid_days) <= MAX_VALID_DAYS:
        raise ValidationError(f"La vigencia va de 1 a {MAX_VALID_DAYS} días.")
    priced = _priced_lines(lines)
    try:
        with transaction.atomic():
            quote = Quote.objects.create(
                client_uuid=client_uuid, customer=customer, customer_name=customer_name[:120],
                customer_phone=(customer_phone or "").strip()[:30], note=(note or "").strip()[:300],
                valid_until=business_date() + timedelta(days=int(valid_days)),
                total=sum((line.total for line in priced), Decimal(0)), created_by=user, duplicated_from=duplicated_from,
            )
            for line in priced:
                line.quote = quote
            QuoteLine.objects.bulk_create(priced)
    except IntegrityError:
        # Dos envíos simultáneos con el mismo client_uuid: la otra ganó.
        return Quote.objects.get(client_uuid=client_uuid), False
    return quote, True


def void_quote(*, quote, user, note):
    """Anula una cotización vigente. Una ajena exige sales.void o reports.view."""
    if quote.created_by_id != user.pk and not can_manage(user):
        raise PermissionDenied("Solo quien hizo la cotización o un supervisor puede anularla.")
    if not (note or "").strip():
        raise ValidationError("Escribe por qué se anula.")
    with transaction.atomic():
        quote = Quote.objects.select_for_update().get(pk=quote.pk)
        status = quote.effective_status()
        if status != Quote.Status.VALID:
            raise ValidationError(f"La cotización {quote.number} está {Quote.Status(status).label.lower()}.")
        quote.status = Quote.Status.VOIDED
        quote.voided_by, quote.voided_at, quote.void_note = user, timezone.now(), note.strip()[:200]
        quote.save(update_fields=["status", "voided_by", "voided_at", "void_note"])
    return quote


def duplicate_quote(*, quote, user, client_uuid, valid_days=DEFAULT_VALID_DAYS):
    """Una cotización nueva con las mismas cantidades y los precios de hoy.

    Devuelve (cotización, creada, skus que se dejaron por fuera porque ya no están a la venta).
    """
    lines = list(quote.lines.select_related("product", "unit"))
    keep = [line for line in lines if line.product.is_active]
    skipped = [line.product.sku for line in lines if not line.product.is_active]
    if not keep:
        raise ValidationError("Ninguno de los productos de esa cotización está a la venta.")
    new, created = create_quote(
        user=user, client_uuid=client_uuid, customer=quote.customer, customer_name=quote.customer_name,
        customer_phone=quote.customer_phone, note=quote.note, valid_days=valid_days, duplicated_from=quote,
        lines=[{"product": line.product, "unit": line.unit, "quantity": line.quantity} for line in keep],
    )
    return new, created, skipped


def _in_orders(line, today=None):
    """(en pedidos pendientes de hoy, cobrado en pedidos pagados) de la línea.

    Lo de un pedido cancelado o vencido no cuenta: vuelve a quedar disponible (decisión 4). De un pedido
    pagado cuenta lo que se cobró, que puede ser menos de lo pedido si el cliente no se llevó todo.
    """
    today = today or business_date()
    pending = charged = Decimal(0)
    for order_line in line.order_lines.select_related("order__sale"):
        order = order_line.order
        status = order.effective_status(today)
        if status == Order.Status.PENDING:
            pending += order_line.quantity
        elif status == Order.Status.PAID:
            sold = order.sale.lines.filter(product=line.product, unit=line.unit).aggregate(q=Sum("quantity"))["q"] or 0
            charged += min(order_line.quantity, sold)
    return pending, charged


def committed(line, today=None):
    """Cuánto de la línea va en pedidos: lo de los pendientes de hoy y lo cobrado de los pagados."""
    return sum(_in_orders(line, today))


def charged(line, today=None):
    """Cuánto de la línea ya se cobró."""
    return _in_orders(line, today)[1]


def remaining(line, today=None):
    """Lo que queda por convertir de la línea (nunca negativo)."""
    return max(line.quantity - committed(line, today), Decimal(0))


def convert_quote(*, quote, user, client_uuid, lines=None):
    """Convierte una parte de la cotización en pedido, con el precio cotizado (decisiones 1 y 4).

    lines: dicts con quote_line (objeto o id) y quantity; None convierte todo lo que queda por convertir.
    Devuelve (pedido, creado). Con el mismo client_uuid devuelve el pedido ya creado, aunque ahora ya
    no quede nada por convertir. Bloquea la cotización: dos conversiones a la vez no pasan de lo cotizado.
    """
    existing = Order.objects.filter(client_uuid=client_uuid).first()
    if existing:
        return existing, False
    with transaction.atomic():
        quote = Quote.objects.select_for_update().get(pk=quote.pk)
        status = quote.effective_status()
        if status != Quote.Status.VALID:
            hint = " Duplícala para cotizar con los precios de hoy." if status == Quote.Status.EXPIRED else ""
            raise ValidationError(f"La cotización {quote.number} está {Quote.Status(status).label.lower()}.{hint}")
        by_id = {line.pk: line for line in quote.lines.select_related("product", "unit")}
        if lines is None:
            chosen = [(line, remaining(line)) for line in by_id.values()]
            chosen = [(line, quantity) for line, quantity in chosen if quantity > 0]
        else:
            wanted = {}
            for item in lines:
                line = by_id.get(getattr(item["quote_line"], "pk", item["quote_line"]))
                if line is None:
                    raise ValidationError("La línea no pertenece a esta cotización.")
                quantity = Decimal(item["quantity"])
                if quantity <= 0:
                    raise ValidationError(f"{line.product.sku}: la cantidad debe ser mayor que cero.")
                wanted[line.pk] = wanted.get(line.pk, Decimal(0)) + quantity
            chosen = []
            for pk, quantity in wanted.items():
                line = by_id[pk]
                left = remaining(line)
                if quantity > left:
                    raise ValidationError(f"{line.product.sku}: quedan {left.normalize():f} {line.unit.code} por convertir.")
                chosen.append((line, quantity))
        if not chosen:
            raise ValidationError(f"La cotización {quote.number} ya no tiene nada por convertir.")
        for line, _ in chosen:
            if not line.product.is_active:
                raise ValidationError(f"{line.product.sku} ya no está a la venta: quítalo de lo que se convierte.")
        return create_order(user=user, client_uuid=client_uuid, lines=[
            {"product": line.product, "unit": line.unit, "quantity": quantity, "unit_price": line.unit_price, "quote_line": line}
            for line, quantity in chosen
        ])


def mark_converted(quote_ids):
    """Después de cobrar un pedido: deja CONVERTIDA la cotización cuyo todo ya se cobró."""
    for quote in Quote.objects.select_for_update().filter(pk__in=quote_ids, status=Quote.Status.VALID):
        if all(charged(line) >= line.quantity for line in quote.lines.all()):
            quote.status = Quote.Status.CONVERTED
            quote.save(update_fields=["status"])


def filter_status(queryset, status, today=None):
    """Filtra por estado efectivo: VALID excluye las vencidas y EXPIRED son las vigentes con la fecha pasada."""
    today = today or business_date()
    if status == Quote.Status.VALID:
        return queryset.filter(status=Quote.Status.VALID, valid_until__gte=today)
    if status == Quote.Status.EXPIRED:
        return queryset.filter(status=Quote.Status.VALID, valid_until__lt=today)
    if status in (Quote.Status.CONVERTED, Quote.Status.VOIDED):
        return queryset.filter(status=status)
    return queryset


def search(queryset, text):
    """Por número (COT-000045 o 45), nombre o teléfono del cliente."""
    text = (text or "").strip()
    if not text:
        return queryset
    condition = Q(customer_name__icontains=text) | Q(customer__name__icontains=text) | Q(customer_phone__icontains=text)
    digits = text.upper().removeprefix("COT-").lstrip("0")
    if digits.isdigit():
        condition |= Q(pk=int(digits))
    return queryset.filter(condition)
