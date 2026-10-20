"""Datos de demostración para mostrar la app a clientes potenciales.

Una ferretería con dos semanas de historia: turnos cerrados con ventas en efectivo, tarjeta y
transferencia, una anulación, una devolución, el arqueo con un faltante, un pedido por cobrar, una
venta sin conexión para revisión, una baja por aprobar, un conteo aprobado, un traslado y un producto
pendiente de precio. Todo pasa por los mismos servicios que usa la app, así el kardex cuadra.

Las fechas se corren hacia atrás después de crear cada documento (los modelos ponen la hora actual).
El azar usa una semilla fija: dos bases sembradas el mismo día quedan iguales.
"""
import random
import secrets
import uuid
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.cash.models import CashRegister, Shift
from apps.cash.services import close_shift, open_shift, shift_summary
from apps.catalog.models import Category, Product, ProductUnit, Unit
from apps.inventory.adjustments import approve_adjustment, create_adjustment
from apps.inventory.counts import approve_count, open_count, record_line, submit_count
from apps.inventory.models import StockMovement, Warehouse
from apps.inventory.services import record_movement
from apps.inventory.transfers import create_transfer
from apps.sales.models import Sale, SaleReturn
from apps.sales.orders import create_order
from apps.sales.returns import create_return, void_sale
from apps.sales.services import catalog_price, create_sale, money

DAYS = 14  # de historia, sin contar hoy

USERS = [  # usuario, nombre, rol
    ("admin.demo", "Administrador", "Administrador"),
    ("marta.jefe", "Marta", "Jefe de bodega"),
    ("pedro.bodega", "Pedro", "Auxiliar de bodega"),
    ("laura.caja", "Laura", "Caja"),
    ("maria.caja", "María", "Caja"),
    ("andres.ventas", "Andrés", "Ventas"),
    ("sofia.super", "Sofía", "Supervisor"),
]

PRODUCTS = [
    # sku, nombre, categoría, unidad, precio, fracción, mínimo, código, presentación (unidad, factor, código), entrada (cantidad base, costo por unidad base)
    ("CAB-12", "Cable THHN calibre 12", "Eléctricos", "m", 3200, True, 50, "7707000000012", ("rollo", 100, "7707000000029"), (600, 1800)),
    ("CAB-14", "Cable THHN calibre 14", "Eléctricos", "m", 2400, True, 50, "7707000000036", ("rollo", 100, "7707000000043"), (500, 1350)),
    ("BOM-LED-9", "Bombillo LED 9 W", "Eléctricos", "und", 6500, False, 20, "7707000000050", ("caja", 10, "7707000000067"), (120, 3600)),
    ("INT-SEN", "Interruptor sencillo", "Eléctricos", "und", 7900, False, 10, "7707000000074", None, (60, 4200)),
    ("MAR-16", "Martillo 16 oz", "Herramientas", "und", 28000, False, 5, "7707000000081", None, (30, 19000)),
    ("LLA-10", "Llave mixta 10 mm", "Herramientas", "und", 18900, False, 5, "7707000000098", None, (25, 11500)),
    ("DES-PH2", "Destornillador de estrella PH2", "Herramientas", "und", 9500, False, 8, "7707000000104", None, (40, 5200)),
    ("FLE-5", "Flexómetro 5 m", "Herramientas", "und", 16500, False, 6, "7707000000111", None, (30, 9800)),
    ("TOR-1/4", "Tornillo drywall 1/4\"", "Tornillería", "und", 150, False, 200, "7707000000128", ("caja", 100, "7707000000135"), (6000, 90)),
    ("CHA-8", "Chazo plástico 8 mm", "Tornillería", "und", 100, False, 300, "7707000000142", ("bolsa", 50, "7707000000159"), (5000, 45)),
    ("PIN-VIN-B", "Pintura vinilo blanco", "Pinturas", "gal", 62000, False, 4, "7707000000166", None, (30, 41000)),
    ("PIN-ESM-N", "Esmalte negro", "Pinturas", "gal", 78000, False, 3, "7707000000173", None, (15, 52000)),
    ("BRO-3", "Brocha de 3 pulgadas", "Pinturas", "und", 8500, False, 10, "7707000000180", None, (50, 4500)),
    ("CEM-50", "Cemento gris 50 kg", "Construcción", "bulto", 34500, False, 20, "7707000000197", None, (80, 27000)),
    ("ALA-18", "Alambre negro calibre 18", "Construcción", "kg", 9800, True, 10, "7707000000203", None, (60, 6500)),
    ("ARE-B", "Arena de pega", "Construcción", "bulto", 9000, False, 10, "7707000000210", None, (60, 5500)),
    ("TUB-PVC-12", "Tubo PVC presión 1/2\"", "Plomería", "und", 14500, False, 10, "7707000000227", None, (50, 9000)),
    ("CIN-TEF", "Cinta de teflón", "Plomería", "und", 2500, False, 30, "7707000000234", ("caja", 20, "7707000000241"), (200, 1100)),
]

EXTRA_UNITS = {"bolsa": "Bolsa"}  # presentaciones que no trae la migración de unidades


def _users(password):
    """Crea los usuarios con su rol. Devuelve {usuario: (objeto, contraseña)}."""
    created = {}
    for username, first_name, role in USERS:
        user = User.objects.create_user(username=username, first_name=first_name)
        secret = password or secrets.token_urlsafe(9)
        user.set_password(secret)
        if username == "admin.demo":
            user.is_staff = user.is_superuser = True  # también entra al admin de Django
        user.save()
        user.roles.set([Role.objects.get(name=role)])
        created[username] = (user, secret)
    return created


def _catalog():
    units = {u.code: u for u in Unit.objects.all()}
    for code, name in EXTRA_UNITS.items():
        if code not in units:
            units[code] = Unit.objects.create(code=code, name=name)
    categories = {}
    products = {}
    for sku, name, category, unit, price, fractions, minimum, barcode, presentation, _ in PRODUCTS:
        if category not in categories:
            categories[category] = Category.objects.create(name=category)
        product = Product.objects.create(
            sku=sku, name=name, category=categories[category], base_unit=units[unit], sale_price=Decimal(price),
            allows_fractions=fractions, min_stock=Decimal(minimum), barcode=barcode,
        )
        if presentation:
            code, factor, unit_barcode = presentation
            ProductUnit.objects.create(product=product, unit=units[code], factor=Decimal(factor), barcode=unit_barcode)
        products[sku] = product
    # Creado desde bodega sin permiso de precios: espera a que el administrador se lo ponga (spec 006).
    Product.objects.create(
        sku="MAN-12", name="Manguera de jardín 1/2\"", category=categories["Plomería"], base_unit=units["m"],
        sale_price=Decimal(0), allows_fractions=True, min_stock=Decimal(20), is_active=False, price_pending=True,
    )
    return units, products


def _at(day, hour, minute=0):
    return day.replace(hour=hour, minute=minute, second=0, microsecond=0)


def _sale(rng, products, cashier, shift, when):
    """Una venta de 1 a 3 productos con el precio del catálogo y un medio de pago al azar."""
    lines, total = [], Decimal(0)
    for product in rng.sample(list(products.values()), rng.randint(1, 3)):
        if product.allows_fractions:
            quantity = Decimal(rng.choice(["2.5", "5", "8", "12.5", "20"]))
        else:
            quantity = Decimal(rng.choice([1, 1, 1, 2, 2, 3, 5]))
        if product.stock_levels.get(warehouse=shift.register.warehouse).quantity - quantity < product.min_stock:
            continue  # que la demo no se quede sin existencias (las ventas en línea no venden en negativo)
        lines.append({"product": product, "quantity": quantity})
        total += money(catalog_price(product, product.base_unit) * quantity)
    if not lines:
        return None
    method = rng.choice(["CASH", "CASH", "CASH", "CARD", "TRANSFER"])
    if method == "CASH":
        received = (total / 1000).to_integral_value(rounding="ROUND_CEILING") * 1000  # paga con billetes
        payments = [{"method": "CASH", "amount": received}]
    else:
        payments = [{"method": method, "amount": total, "reference": f"{method[:3]}-{rng.randint(10000, 99999)}"}]
    sale, _ = create_sale(user=cashier, shift=shift, client_uuid=uuid.uuid4(), lines=lines, payments=payments, occurred_at=when)
    Sale.objects.filter(pk=sale.pk).update(created_at=when)
    return sale


def _worked_days(now):
    """Los días de historia en que abre la caja (los domingos no) y en cuáles van los casos especiales.

    Devuelve (días, (anulación, devolución, faltante, entrada a otro precio)). Los casos se cuentan sobre
    los días trabajados, no "hace N días", para que no se pierdan cuando ese día cae en domingo.
    """
    worked = [day for day in (now - timedelta(days=back) for back in range(DAYS, 0, -1)) if day.weekday() != 6]
    return worked, (worked[-3], worked[-2], worked[-5], worked[len(worked) // 2])


def _history(rng, now, users, warehouse, registers, products):
    """Dos semanas de turnos cerrados en la caja 1, con una anulación, una devolución y un faltante."""
    laura, sofia = users["laura.caja"][0], users["sofia.super"][0]
    worked, (void_day, return_day, short_day, restock_day) = _worked_days(now)
    for day in worked:
        shift = open_shift(register=registers["CAJA1"], user=laura, opening_float=Decimal(150000))
        sales = [
            _sale(rng, products, laura, shift, _at(day, hour, rng.randint(0, 59)))
            for hour in sorted(rng.sample(range(8, 18), rng.randint(4, 8)))
        ]
        sales = [s for s in sales if s]
        if day == void_day:
            void_sale(sale=sales[0], user=sofia, reason="El cliente se arrepintió antes de salir")
            Sale.objects.filter(pk=sales[0].pk).update(voided_at=_at(day, 17, 30))
            StockMovement.objects.filter(reference=f"Anulación {sales[0].number}").update(occurred_at=_at(day, 17, 30))
        if day == return_day:
            line = sales[-1].lines.first()
            sale_return, _ = create_return(
                sale=sales[-1], user=sofia, shift=shift, lines=[{"sale_line": line, "quantity": line.quantity}],
                refund_method="CASH", reason="Producto equivocado", client_uuid=uuid.uuid4(),
            )
            SaleReturn.objects.filter(pk=sale_return.pk).update(created_at=_at(day, 17, 45))
            StockMovement.objects.filter(reference=f"Devolución {sale_return.number} de {sales[-1].number}").update(
                occurred_at=_at(day, 17, 45),
            )
        expected = shift_summary(shift)["expected_cash"]
        short = Decimal(2000) if day == short_day else Decimal(0)
        close_shift(shift=shift, user=laura, counted_cash=expected - short, notes="Faltan 2.000" if short else "")
        Shift.objects.filter(pk=shift.pk).update(opened_at=_at(day, 7, 50), closed_at=_at(day, 18, 10))
        if day == restock_day:  # llega mercancía a otro precio: el costo promedio se mueve (spec 004)
            for sku, quantity, cost in (("MAR-16", 12, 21000), ("CEM-50", 40, 28500)):
                record_movement(
                    kind=StockMovement.Kind.RECEIPT, product=products[sku], warehouse=warehouse, quantity=quantity,
                    unit_cost=Decimal(cost), user=users["pedro.bodega"][0], reference="Factura proveedor FAC-2210",
                    occurred_at=_at(day, 18, 30),
                )


def _today(rng, now, users, warehouses, registers, products):
    """Hoy: caja abierta con ventas, una venta para revisión, el inventario del día y un pedido por cobrar.

    Las ventas van antes que el conteo: una venta con hora anterior a un conteo aprobado que llegara
    después quedaría marcada como tardía (spec 006, decisión 3).
    """
    marta, pedro, laura = users["marta.jefe"][0], users["pedro.bodega"][0], users["laura.caja"][0]
    # Caja abierta con las ventas de la mañana.
    shift = open_shift(register=registers["CAJA1"], user=laura, opening_float=Decimal(150000))
    Shift.objects.filter(pk=shift.pk).update(opened_at=min(now, _at(now, 7, 50)))
    for minutes in (20, 75, 130):
        _sale(rng, products, laura, shift, min(now, _at(now, 8) + timedelta(minutes=minutes)))
    # Venta hecha sin conexión con el precio viejo de la pintura: queda para revisión.
    create_sale(
        user=laura, shift=shift, client_uuid=uuid.uuid4(), offline=True, occurred_at=min(now, _at(now, 9, 40)),
        lines=[{"product": products["PIN-VIN-B"], "quantity": 1, "unit_price": Decimal(60000)}],
        payments=[{"method": "CASH", "amount": Decimal(60000)}],
    )
    # Baja por aprobar: la pidió bodega y la aprueba el jefe.
    create_adjustment(
        user=pedro, client_uuid=uuid.uuid4(), warehouse=warehouses["PRAL"], reason="DAMAGE",
        note="Se rompieron dos bombillos al bajar la caja", lines=[{"product": products["BOM-LED-9"], "quantity": 2, "direction": "OUT"}],
    )
    # Una baja ya aprobada, para que se vea en el historial y en el kardex.
    used, _ = create_adjustment(
        user=pedro, client_uuid=uuid.uuid4(), warehouse=warehouses["PRAL"], reason="INTERNAL_USE",
        note="Brocha para pintar el mostrador", lines=[{"product": products["BRO-3"], "quantity": 1, "direction": "OUT"}],
    )
    approve_adjustment(adjustment=used, user=marta)
    # Conteo ciego de pinturas, aprobado con una diferencia.
    count, _ = open_count(user=pedro, client_uuid=uuid.uuid4(), warehouse=warehouses["PRAL"], category=products["PIN-VIN-B"].category)
    for line in count.lines.select_related("product"):
        level = line.product.stock_levels.get(warehouse=warehouses["PRAL"]).quantity
        found = level - 1 if line.product.sku == "PIN-ESM-N" else level  # falta un galón de esmalte
        record_line(count=count, line=line, user=pedro, quantity=found)
    submit_count(count=count)
    approve_count(count=count, user=marta)
    # Se surte la vitrina del local.
    create_transfer(
        user=marta, client_uuid=uuid.uuid4(), origin=warehouses["PRAL"], destination=warehouses["VIT"],
        note="Surtir la vitrina", lines=[
            {"product": products["BOM-LED-9"], "quantity": 1, "unit": products["BOM-LED-9"].units.get().unit},
            {"product": products["FLE-5"], "quantity": 4},
        ],
    )
    # Pedido del vendedor esperando en caja.
    create_order(user=users["andres.ventas"][0], client_uuid=uuid.uuid4(), lines=[
        {"product": products["CEM-50"], "quantity": 4}, {"product": products["ARE-B"], "quantity": 6},
    ])


def seed(*, password=None, now=None, rng_seed=2026):
    """Siembra una base recién migrada. Devuelve {usuario: contraseña}."""
    if Product.objects.exists() or Sale.objects.exists():
        raise ValidationError("La base ya tiene datos: usa --fresh para empezar de cero.")
    now = timezone.localtime(now or timezone.now())
    rng = random.Random(rng_seed)
    with transaction.atomic():
        users = _users(password)
        warehouses = {
            "PRAL": Warehouse.objects.create(code="PRAL", name="Bodega principal"),
            "VIT": Warehouse.objects.create(code="VIT", name="Vitrina del local"),
        }
        registers = {
            code: CashRegister.objects.create(code=code, name=name, warehouse=warehouses["PRAL"])
            for code, name in (("CAJA1", "Caja 1"), ("CAJA2", "Caja 2"))
        }
        _, products = _catalog()
        start = _at(now - timedelta(days=DAYS + 1), 9)
        for sku, *_rest, (quantity, cost) in PRODUCTS:
            record_movement(
                kind=StockMovement.Kind.RECEIPT, product=products[sku], warehouse=warehouses["PRAL"], quantity=quantity,
                unit_cost=Decimal(cost), user=users["pedro.bodega"][0], reference="Factura proveedor FAC-1043", occurred_at=start,
            )
        _history(rng, now, users, warehouses["PRAL"], registers, products)
        _today(rng, now, users, warehouses, registers, products)
    return {username: secret for username, (_, secret) in users.items()}
