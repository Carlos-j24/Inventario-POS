"""Conteos físicos (spec 006, T5).

Reglas:
- Se abre un conteo para una bodega, completa o de una categoría: productos activos y los inactivos
  que todavía tienen existencias ahí. Un producto no puede estar en dos conteos abiertos de la misma
  bodega.
- Conteo ciego: se guarda lo contado (en unidad base) y la hora en que se contó cada línea.
- Al aprobar, lo esperado es la suma de los movimientos con occurred_at hasta la hora de la línea, así
  la caja sigue vendiendo durante el conteo (decisión 3). Lo que no se contó no se ajusta, salvo que el
  aprobador lo marque en 0 (decisión 7). Las diferencias generan un ajuste "Conteo físico" ya aprobado.
"""
import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q, Sum
from django.utils import timezone

from apps.catalog.models import Product
from apps.catalog.units import to_base_quantity

from .adjustments import approve_adjustment, create_adjustment
from .models import Adjustment, CountLine, PhysicalCount, StockMovement, Warehouse

Status = PhysicalCount.Status
ACTIVE = (Status.OPEN, Status.SUBMITTED)
COUNTERS = ("inventory.count", "inventory.adjust")
NAMESPACE = uuid.UUID("6f0c4f0e-5d0b-4f8a-9a2f-0c0a7b1d2e3f")  # para que el ajuste de un conteo sea siempre el mismo


def products_for(warehouse, category=None):
    """Lo que se cuenta: productos activos y los inactivos que aún tienen existencias en la bodega."""
    has_stock = Q(stock_levels__warehouse=warehouse) & ~Q(stock_levels__quantity=0)
    products = Product.objects.filter(Q(is_active=True) | has_stock)
    if category is not None:
        products = products.filter(category=category)
    return products.distinct().order_by("name")


def open_count(*, user, client_uuid, warehouse, category=None):
    """Abre el conteo con su lista de productos. Devuelve (conteo, creado)."""
    existing = PhysicalCount.objects.filter(client_uuid=client_uuid).first()
    if existing:
        # Reintento: sin esto chocaría con la regla de "ya hay un conteo abierto con esos productos".
        return existing, False
    products = list(products_for(warehouse, category))
    if not products:
        raise ValidationError("No hay productos para contar con ese filtro.")
    try:
        with transaction.atomic():
            # Bloquear la bodega evita que dos conteos que se cruzan se abran a la vez.
            Warehouse.objects.select_for_update().get(pk=warehouse.pk)
            busy = (
                CountLine.objects.filter(count__warehouse=warehouse, count__status__in=ACTIVE, product__in=products)
                .select_related("count", "product")
            )
            if busy.exists():
                numbers = sorted({line.count.number for line in busy})
                skus = ", ".join(sorted({line.product.sku for line in busy})[:5])
                raise ValidationError(f"Ya hay un conteo abierto con esos productos ({', '.join(numbers)}: {skus}…). Termínalo o anúlalo antes.")
            count = PhysicalCount.objects.create(client_uuid=client_uuid, warehouse=warehouse, category=category, opened_by=user)
            CountLine.objects.bulk_create(CountLine(count=count, product=p) for p in products)
    except IntegrityError:
        return PhysicalCount.objects.get(client_uuid=client_uuid), False  # reintento con el mismo client_uuid
    return count, True


def _lock(count, *allowed):
    count = PhysicalCount.objects.select_for_update().get(pk=count.pk)
    if count.status not in allowed:
        raise ValidationError(f"El conteo {count.number} está {count.get_status_display().lower()}.")
    return count


def record_line(*, count, line, user, quantity, unit=None):
    """Guarda lo contado de una línea (se puede volver a contar mientras el conteo esté abierto)."""
    with transaction.atomic():
        _lock(count, Status.OPEN)
        line = CountLine.objects.select_for_update().select_related("product").get(pk=line.pk, count=count)
        quantity = Decimal(quantity)
        if quantity < 0:
            raise ValidationError("Lo contado no puede ser negativo.")
        line.counted = to_base_quantity(line.product, quantity, unit)
        line.counted_at, line.counted_by, line.marked_zero = timezone.now(), user, False
        line.save(update_fields=["counted", "counted_at", "counted_by", "marked_zero"])
    return line


def submit_count(*, count):
    """Termina de contar y lo deja para aprobación."""
    with transaction.atomic():
        count = _lock(count, Status.OPEN)
        if not count.lines.filter(counted__isnull=False).exists():
            raise ValidationError("No has contado ningún producto.")
        count.status, count.submitted_at = Status.SUBMITTED, timezone.now()
        count.save(update_fields=["status", "submitted_at"])
    return count


def expected_at(product, warehouse, moment):
    """Lo que decía el sistema a esa hora: los movimientos que ocurrieron hasta entonces."""
    total = StockMovement.objects.filter(product=product, warehouse=warehouse, occurred_at__lte=moment).aggregate(q=Sum("quantity"))["q"]
    return total or Decimal(0)


def approve_count(*, count, user, zero_uncounted=()):
    """Calcula las diferencias y las aplica con un ajuste "Conteo físico". zero_uncounted: "all" o ids."""
    with transaction.atomic():
        count = _lock(count, Status.SUBMITTED)
        now = timezone.now()
        differences = []
        for line in count.lines.select_related("product"):
            if line.counted is None and (zero_uncounted == "all" or line.pk in set(zero_uncounted)):
                line.counted, line.counted_at, line.counted_by, line.marked_zero = Decimal(0), now, user, True
            if line.counted is None:
                continue  # no se contó: no se ajusta (decisión 7)
            line.expected = expected_at(line.product, count.warehouse, line.counted_at)
            line.difference = line.counted - line.expected
            line.save(update_fields=["counted", "counted_at", "counted_by", "marked_zero", "expected", "difference"])
            if line.difference != 0:
                differences.append(line)
        if differences:
            adjustment, _ = create_adjustment(
                user=user, client_uuid=uuid.uuid5(NAMESPACE, f"count-{count.pk}"), warehouse=count.warehouse,
                reason=Adjustment.Reason.PHYSICAL_COUNT, note=f"Conteo físico {count.number}", system=True,
                lines=[
                    {"product": line.product, "quantity": abs(line.difference), "direction": "IN" if line.difference > 0 else "OUT"}
                    for line in differences
                ],
            )
            count.adjustment = approve_adjustment(adjustment=adjustment, user=user)
        count.status, count.decided_by, count.decided_at = Status.APPROVED, user, now
        count.save(update_fields=["status", "decided_by", "decided_at", "adjustment"])
    return count


def void_count(*, count, user, note):
    if not (note or "").strip():
        raise ValidationError("Escribe por qué se anula.")
    with transaction.atomic():
        count = _lock(count, *ACTIVE)
        count.status, count.decided_by, count.decided_at = Status.VOIDED, user, timezone.now()
        count.void_note = note.strip()[:200]
        count.save(update_fields=["status", "decided_by", "decided_at", "void_note"])
    return count
