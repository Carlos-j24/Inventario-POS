"""Cotizaciones: modelos y servicio (spec 007, T1)."""
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction

from apps.catalog.models import Unit
from apps.customers.models import Customer
from apps.inventory.models import StockMovement
from apps.inventory.services import record_movement

from . import quotes as service
from .models import Order, OrderLine, Quote, business_date
from .orders import cancel_order, create_order
from .services import create_sale

pytestmark = pytest.mark.django_db
CASH = [{"method": "CASH", "amount": Decimal("10000000")}]


@pytest.fixture
def vendor(make_user):
    return make_user("andres", "Ventas")


@pytest.fixture
def builder(db):
    return Customer.objects.create(id_number="900123456", name="Constructora Los Pinos")


def quote(user, *lines, **extra):
    data = {"customer_name": "Don Jorge (maestro)", **extra}
    q, _ = service.create_quote(user=user, client_uuid=uuid.uuid4(), lines=list(lines), **data)
    return q


def line(product, quantity, unit=None):
    item = {"product": product, "quantity": Decimal(str(quantity))}
    if unit:
        item["unit"] = Unit.objects.get(code=unit)
    return item


# --- crear ---------------------------------------------------------------------

def test_freezes_catalog_prices_and_tax_and_lasts_eight_days(vendor, hammer, cable):
    q = quote(vendor, line(cable, 2, "rollo"), line(cable, "12.5"), line(hammer, 3), customer_phone=" 3001234567 ", note=" Entrega en obra ")
    assert q.number == f"COT-{q.pk:06d}"
    assert (q.created_by, q.customer_label, q.customer_phone, q.note) == (vendor, "Don Jorge (maestro)", "3001234567", "Entrega en obra")
    assert q.valid_until == business_date() + timedelta(days=8)
    assert q.effective_status() == Quote.Status.VALID
    rows = [(l.unit.code, l.quantity, l.unit_price, l.tax_rate, l.vat_excluded, l.total) for l in q.lines.all()]
    assert rows == [
        ("rollo", Decimal("2.000"), Decimal("320000.00"), "19", False, Decimal("640000.00")),  # 100 m × 3.200
        ("m", Decimal("12.500"), Decimal("3200.00"), "19", False, Decimal("40000.00")),
        ("und", Decimal("3.000"), Decimal("28000.00"), "19", False, Decimal("84000.00")),
    ]
    assert q.total == Decimal("764000.00")
    # Lo cotizado no cambia si después cambia el catálogo.
    hammer.sale_price = Decimal("31000")
    hammer.save()
    assert q.lines.get(product=hammer).unit_price == Decimal("28000.00")


def test_custom_validity_and_a_registered_customer(vendor, hammer, builder):
    q = quote(vendor, line(hammer, 1), customer_name="", customer=builder, valid_days=30)
    assert (q.customer_label, q.customer_name, q.valid_until) == ("Constructora Los Pinos", "", business_date() + timedelta(days=30))
    assert quote(vendor, line(hammer, 1), valid_days=1).valid_until == business_date() + timedelta(days=1)


@pytest.mark.parametrize("change, message", [
    ({"lines": []}, "no tiene líneas"),
    ({"quantity": "0"}, "MAR-16: la cantidad debe ser mayor que cero"),
    ({"quantity": "1.5"}, "no se vende fraccionado"),
    ({"unit": "rollo"}, "no se maneja en la unidad"),
    ({"customer_name": "   "}, "Escribe a nombre de quién va"),
    ({"valid_days": 0}, "La vigencia va de 1 a 30 días"),
    ({"valid_days": 31}, "La vigencia va de 1 a 30 días"),
    ({"twice": True}, "MAR-16 está dos veces en und: junta las cantidades"),
    ({"inactive": True}, "MAR-16 no está a la venta"),
])
def test_invalid_quotes(vendor, hammer, change, message):
    if change.get("inactive"):
        hammer.is_active = False
        hammer.save()
    item = line(hammer, change.get("quantity", 1), change.get("unit"))
    lines = change.get("lines", [item, item] if change.get("twice") else [item])
    extra = {k: change[k] for k in ("customer_name", "valid_days") if k in change}
    with pytest.raises(ValidationError, match=message):
        service.create_quote(user=vendor, client_uuid=uuid.uuid4(), lines=lines, **{"customer_name": "X", **extra})
    assert not Quote.objects.exists()


def test_same_product_in_two_units_is_fine(vendor, cable):
    assert quote(vendor, line(cable, 1, "rollo"), line(cable, 30)).lines.count() == 2


def test_an_inactive_customer_cannot_be_quoted(vendor, hammer, builder):
    builder.is_active = False
    builder.save()
    with pytest.raises(ValidationError, match="Ese cliente está inactivo"):
        quote(vendor, line(hammer, 1), customer=builder)


def test_same_client_uuid_creates_one_quote(vendor, hammer):
    key = uuid.uuid4()
    first, created = service.create_quote(user=vendor, client_uuid=key, lines=[line(hammer, 1)], customer_name="A")
    again, created_again = service.create_quote(user=vendor, client_uuid=key, lines=[line(hammer, 5)], customer_name="B")
    assert (created, created_again, again.pk, Quote.objects.count()) == (True, False, first.pk, 1)
    # Un reintento devuelve la que quedó aunque ahora no se pudiera cotizar.
    hammer.is_active = False
    hammer.save()
    assert service.create_quote(user=vendor, client_uuid=key, lines=[line(hammer, 1)], customer_name="A")[0].pk == first.pk


def test_keeps_the_tax_rate_and_exclusion_of_each_product(vendor, hammer):
    hammer.tax_rate, hammer.vat_excluded = "0", True
    hammer.save()
    q = quote(vendor, line(hammer, 1))
    assert (q.lines.get().tax_rate, q.lines.get().vat_excluded) == ("0", True)


def test_database_requires_a_customer_and_never_stores_expired(vendor):
    base = {"valid_until": business_date(), "total": 0, "created_by": vendor}
    with pytest.raises(IntegrityError), transaction.atomic():
        Quote.objects.create(client_uuid=uuid.uuid4(), **base)
    with pytest.raises(IntegrityError), transaction.atomic():
        Quote.objects.create(client_uuid=uuid.uuid4(), customer_name="A", status="EXPIRED", **base)


# --- vencer, anular y duplicar --------------------------------------------------

def test_expires_the_day_after_valid_until(vendor, hammer):
    q = quote(vendor, line(hammer, 1), valid_days=1)
    assert q.effective_status(today=q.valid_until) == Quote.Status.VALID
    assert q.effective_status(today=q.valid_until + timedelta(days=1)) == Quote.Status.EXPIRED
    q.status = Quote.Status.VOIDED
    assert q.effective_status(today=q.valid_until + timedelta(days=1)) == Quote.Status.VOIDED


def test_void_own_or_with_permission_and_a_reason(make_user, vendor, hammer):
    q = quote(vendor, line(hammer, 1))
    with pytest.raises(PermissionDenied):
        service.void_quote(quote=q, user=make_user("otro", "Ventas"), note="No")
    with pytest.raises(ValidationError, match="Escribe por qué se anula"):
        service.void_quote(quote=q, user=vendor, note="  ")
    q = service.void_quote(quote=q, user=vendor, note=" El cliente compró en otro lado ")
    assert (q.status, q.voided_by, q.void_note) == (Quote.Status.VOIDED, vendor, "El cliente compró en otro lado")
    assert q.voided_at is not None
    with pytest.raises(ValidationError, match=f"La cotización {q.number} está anulada"):
        service.void_quote(quote=q, user=vendor, note="Otra vez")
    other = quote(vendor, line(hammer, 1))
    for role in ("Supervisor", "Administrador", "Jefe de bodega"):  # el jefe tiene reports.view sin sales.void
        assert service.can_manage(make_user(role, role))
    assert not service.can_manage(make_user("caja", "Caja"))
    assert service.void_quote(quote=other, user=make_user("sofia", "Supervisor"), note="Repetida").status == Quote.Status.VOIDED


def test_an_expired_quote_cannot_be_voided(vendor, hammer):
    q = quote(vendor, line(hammer, 1))
    Quote.objects.filter(pk=q.pk).update(valid_until=business_date() - timedelta(days=1))
    with pytest.raises(ValidationError, match="está vencida"):
        service.void_quote(quote=q, user=vendor, note="Vieja")


def test_duplicate_with_todays_prices_and_without_what_is_no_longer_sold(vendor, hammer, cable, builder):
    old = quote(vendor, line(hammer, 3), line(cable, 1, "rollo"), customer=builder, customer_phone="300", note="Obra")
    Quote.objects.filter(pk=old.pk).update(valid_until=business_date() - timedelta(days=2))  # vencida
    hammer.sale_price = Decimal("31000")
    hammer.save()
    cable.is_active = False
    cable.save()
    new, created, skipped = service.duplicate_quote(quote=old, user=vendor, client_uuid=uuid.uuid4(), valid_days=15)
    assert (created, skipped, new.duplicated_from, new.effective_status()) == (True, ["CAB-12"], old, Quote.Status.VALID)
    assert (new.customer, new.customer_name, new.customer_phone, new.note) == (builder, "Don Jorge (maestro)", "300", "Obra")
    assert new.valid_until == business_date() + timedelta(days=15)
    assert [(l.product.sku, l.quantity, l.unit_price) for l in new.lines.all()] == [("MAR-16", Decimal("3.000"), Decimal("31000.00"))]
    assert new.total == Decimal("93000.00")

    hammer.is_active = False
    hammer.save()
    with pytest.raises(ValidationError, match="Ninguno de los productos"):
        service.duplicate_quote(quote=old, user=vendor, client_uuid=uuid.uuid4())


# --- por convertir ---------------------------------------------------------------

@pytest.fixture
def stocked(vendor, warehouse, hammer, cable):
    for product, qty in ((hammer, 20), (cable, 500)):
        record_movement(kind=StockMovement.Kind.RECEIPT, product=product, warehouse=warehouse, quantity=qty, user=vendor)


def order_from(vendor, quote_line, quantity):
    """Lo que hará la T2: un pedido con una parte de la línea cotizada."""
    order, _ = create_order(user=vendor, client_uuid=uuid.uuid4(), lines=[
        {"product": quote_line.product, "unit": quote_line.unit, "quantity": Decimal(quantity)},
    ])
    order.lines.update(quote_line=quote_line)
    return order


@pytest.mark.usefixtures("stocked")
def test_remaining_counts_pending_and_charged_orders_only(make_user, vendor, shift, hammer):
    q = quote(vendor, line(hammer, 10))
    hammers = q.lines.get()
    assert (service.committed(hammers), service.remaining(hammers)) == (0, 10)

    order_from(vendor, hammers, 3)  # pendiente de hoy: comprometido
    assert service.remaining(hammers) == 7

    cancelled = order_from(vendor, hammers, 2)
    cancel_order(order=cancelled, user=vendor)  # cancelado: vuelve a quedar disponible
    assert service.remaining(hammers) == 7

    old = order_from(vendor, hammers, 4)
    Order.objects.filter(pk=old.pk).update(business_date=business_date() - timedelta(days=1))  # vencido
    assert service.remaining(hammers) == 7

    paid = order_from(vendor, hammers, 5)
    order_line = paid.lines.get()
    create_sale(user=make_user("laura", "Caja"), shift=shift, order=paid, client_uuid=uuid.uuid4(), payments=CASH,
                lines=[{"order_line": order_line, "quantity": Decimal(2)}])  # el cliente se llevó solo 2
    assert (service.committed(hammers), service.remaining(hammers)) == (5, 5)  # 3 pendientes + 2 cobrados


@pytest.mark.usefixtures("stocked")
def test_remaining_never_goes_below_zero_and_matches_the_unit(vendor, cable):
    q = quote(vendor, line(cable, 1, "rollo"), line(cable, 20))
    rolls, meters = q.lines.order_by("pk")
    order_from(vendor, meters, 25)  # un pedido viejo de más (la T2 no lo dejará)
    assert service.remaining(meters) == 0
    assert service.remaining(rolls) == 1  # los metros no tocan los rollos


# --- buscar y filtrar -------------------------------------------------------------

def test_filter_by_effective_status_and_search(vendor, hammer, builder):
    valid = quote(vendor, line(hammer, 1), customer_name="Don Jorge", customer_phone="3001112233")
    expired = quote(vendor, line(hammer, 1), customer_name="Doña Rosa")
    Quote.objects.filter(pk=expired.pk).update(valid_until=business_date() - timedelta(days=1))
    voided = service.void_quote(quote=quote(vendor, line(hammer, 1), customer=builder, customer_name=""), user=vendor, note="X")
    converted = quote(vendor, line(hammer, 1), customer_name="Ana")
    Quote.objects.filter(pk=converted.pk).update(status=Quote.Status.CONVERTED)

    def ids(qs):
        return set(qs.values_list("pk", flat=True))

    every = Quote.objects.all()
    assert ids(service.filter_status(every, "VALID")) == {valid.pk}
    assert ids(service.filter_status(every, "EXPIRED")) == {expired.pk}
    assert ids(service.filter_status(every, "VOIDED")) == {voided.pk}
    assert ids(service.filter_status(every, "CONVERTED")) == {converted.pk}
    assert ids(service.filter_status(every, "")) == ids(every)
    assert ids(service.search(every, "jorge")) == {valid.pk}
    assert ids(service.search(every, "111")) == {valid.pk}
    assert ids(service.search(every, "pinos")) == {voided.pk}  # por el cliente registrado
    assert ids(service.search(every, valid.number.lower())) == {valid.pk}
    assert expired.pk in ids(service.search(every, str(expired.pk)))  # el número sin COT- (también busca en teléfonos)
    assert ids(service.search(every, "  ")) == ids(every)
