"""Demo de un taller de motos con repuestos (spec 009, T4): `seed_demo --taller`.

La misma historia que la ferretería (turnos, anulación, devolución, faltante, venta para revisión,
conteo, traslado, pedido y cotizaciones) con repuestos de moto, más el módulo de taller activo,
una recepcionista y clientes con sus motos: una con dueño anterior, una sin placa y lecturas de
kilometraje de los últimos meses. Los datos del negocio son ficticios.
"""
import uuid
from datetime import timedelta
from decimal import Decimal

from apps.cash.models import Shift
from apps.cash.services import open_shift
from apps.catalog.models import Unit
from apps.customers.models import Customer
from apps.customers.rules import check_digit
from apps.inventory.adjustments import approve_adjustment, create_adjustment
from apps.inventory.counts import approve_count, open_count, record_line, submit_count
from apps.inventory.transfers import create_transfer
from apps.invoicing.models import Business
from apps.sales.models import Quote, Sale
from apps.sales.orders import create_order
from apps.sales.quotes import convert_quote, create_quote, void_quote
from apps.sales.services import create_sale
from apps.workshop.models import MileageReading, Motorcycle, Ownership
from apps.workshop.services import change_owner, register_motorcycle, update_mileage

from .seed import USERS, Profile, _at, _sale

PRODUCTS = (
    # sku, nombre, categoría, unidad, precio, fracción, mínimo, código, presentación (unidad, factor, código), entrada (cantidad base, costo)
    ("CAB-16", "Cable automotriz calibre 16", "Eléctricos", "m", 2800, True, 50, "7707100000012", ("rollo", 100, "7707100000029"), (600, 1500)),
    ("MAN-GAS", "Manguera de gasolina 1/4\"", "Motor", "m", 4500, True, 30, "7707100000036", ("rollo", 50, "7707100000043"), (300, 2400)),
    ("BOM-H4", "Bombillo LED farola H4", "Eléctricos", "und", 18000, False, 10, "7707100000050", ("caja", 10, "7707100000067"), (120, 9500)),
    ("BUJ-C7", "Bujía NGK C7HSA", "Motor", "und", 12000, False, 20, "7707100000074", None, (100, 6800)),
    ("KIT-BOX100", "Kit de arrastre Boxer 100", "Transmisión", "und", 98000, False, 4, "7707100000081", None, (25, 64000)),
    ("PAS-DEL", "Pastillas de freno delanteras", "Frenos", "par", 28000, False, 6, "7707100000098", None, (40, 15500)),
    ("BAN-TRA", "Bandas de freno traseras", "Frenos", "par", 22000, False, 6, "7707100000104", None, (40, 12000)),
    ("FIL-P200", "Filtro de aire Pulsar 200", "Motor", "und", 26000, False, 6, "7707100000111", None, (30, 14000)),
    ("TOR-M6", "Tornillo de carenaje M6", "Tornillería", "und", 500, False, 200, "7707100000128", ("caja", 100, "7707100000135"), (6000, 220)),
    ("ARA-CU", "Arandela de cobre tapón de cárter", "Tornillería", "und", 300, False, 300, "7707100000142", ("bolsa", 50, "7707100000159"), (5000, 120)),
    ("ACE-20W50", "Aceite 4T 20W50 x 1 L", "Lubricantes", "und", 32000, False, 12, "7707100000166", None, (80, 21000)),
    ("ACE-10W40", "Aceite sintético 10W40 x 1 L", "Lubricantes", "und", 48000, False, 6, "7707100000173", None, (30, 31000)),
    ("GRA-CAD", "Grasa para cadena en spray", "Lubricantes", "und", 24000, False, 6, "7707100000180", None, (40, 14500)),
    ("LLA-90-18", "Llanta trasera 90/90-18", "Llantas", "und", 135000, False, 4, "7707100000197", None, (40, 98000)),
    ("CAB-BUJ", "Cable de bujía", "Eléctricos", "m", 6000, True, 10, "7707100000203", None, (60, 3200)),
    ("LLA-275-18", "Llanta delantera 2.75-18", "Llantas", "und", 115000, False, 4, "7707100000210", None, (40, 82000)),
    ("CAD-428", "Cadena 428H x 120 eslabones", "Transmisión", "und", 55000, False, 6, "7707100000227", None, (50, 34000)),
    ("FUS-15", "Fusible de cuchilla 15 A", "Eléctricos", "und", 1000, False, 30, "7707100000234", ("caja", 20, "7707100000241"), (200, 400)),
)

PENDING = {"sku": "DIR-LED", "name": "Direccional LED universal", "category": "Eléctricos", "unit": "und", "fractions": False, "minimum": 10}
RESTOCK = (("KIT-BOX100", 10, 69000), ("LLA-90-18", 12, 104000))

# Clientes del taller (cédula o NIT, nombre, teléfono) y sus motos. Placas y chasis ficticios.
CUSTOMERS = {
    "jorge": ("13", "79123456", "Jorge Ramírez", "300 123 4567"),
    "ana": ("13", "52111222", "Ana Pérez", "310 999 8877"),
    "luis": ("13", "1010202030", "Luis Gómez", "312 555 7788"),
}
FLEET = "Mensajería Express del Caquetá S.A.S."


def _business():
    business = Business.load()
    business.name, business.trade_name = "Motos y Repuestos La 16 S.A.S.", "Motos La 16"
    business.nit = "900555111"
    business.check_digit = check_digit(business.nit)
    business.address, business.city = "Carrera 11 # 16-20", "Florencia, Caquetá"
    business.phone, business.email = "608 435 1234", "taller@motosla16.example"
    business.tax_regime = "Responsable de IVA"
    business.workshop_enabled = True  # spec 009: el módulo de taller
    business.save()


def _fleet():
    return Customer.objects.get_or_create(
        id_type="31", id_number="901234567",
        defaults={"person_type": "1", "check_digit": check_digit("901234567"), "name": FLEET, "phone": "310 555 0101"},
    )[0]


def _quotes(now, users, products, shift):
    """Cotizaciones de trabajos: vigente, por partes, convertida, vencida y anulada (como la ferretería)."""
    andres, laura = users["andres.ventas"][0], users["laura.caja"][0]
    units = {u.code: u for u in Unit.objects.filter(code__in=["caja", "bolsa", "rollo"])}

    def quote(lines, *, back=0, **who):
        q, _ = create_quote(user=andres, client_uuid=uuid.uuid4(), lines=[
            {"product": products[sku], "quantity": Decimal(qty), **({"unit": units[unit]} if unit else {})}
            for sku, qty, unit in lines
        ], **who)
        if back:  # se hizo hace unos días: la vigencia corre desde entonces
            Quote.objects.filter(pk=q.pk).update(
                created_at=_at(now - timedelta(days=back), 10), valid_until=q.valid_until - timedelta(days=back),
            )
            q.refresh_from_db()
        return q

    def charge(q, parts=None):
        lines = None if parts is None else [
            {"quote_line": q.lines.get(product=products[sku]), "quantity": Decimal(qty)} for sku, qty in parts
        ]
        order, _ = convert_quote(quote=q, user=andres, client_uuid=uuid.uuid4(), lines=lines)
        sale, _ = create_sale(user=laura, shift=shift, order=order, lines=None, client_uuid=uuid.uuid4(),
                              payments=[{"method": "CASH", "amount": order.total}])
        Sale.objects.filter(pk=sale.pk).update(created_at=sale.occurred_at)

    quote([("LLA-90-18", 1, None), ("LLA-275-18", 1, None), ("CAD-428", 1, None), ("KIT-BOX100", 1, None)],
          customer_name="Jorge Ramírez (Boxer XYZ12A)", customer_phone="3001234567",
          note="Cambio de llantas y kit de arrastre. Mano de obra aparte")
    partial = quote([("ARA-CU", 2, "bolsa"), ("BUJ-C7", 10, None), ("PAS-DEL", 6, None)], back=2,
                    customer=_fleet(), note="Mantenimiento preventivo de la flota (10 motos)")
    charge(partial, [("ARA-CU", 1), ("BUJ-C7", 10)])
    charge(quote([("ACE-10W40", 2, None), ("FIL-P200", 1, None), ("BUJ-C7", 1, None)], back=1,
                 customer_name="Ana Pérez (Pulsar ABC34D)", customer_phone="3109998877"))
    quote([("PAS-DEL", 1, None), ("BAN-TRA", 1, None)], back=12, customer_name="Luis Gómez")
    void_quote(quote=quote([("FIL-P200", 1, None)], customer_name="Cliente de paso"), user=andres,
               note="El cliente decidió esperar")


def _motorcycles(now, users):
    """Motos de ejemplo con su historia: lecturas de meses atrás, una vendida a otro dueño y una sin placa."""
    diana = users["diana.recepcion"][0]
    people = {
        key: Customer.objects.create(id_type=t, id_number=n, name=name, phone=phone, check_digit="")
        for key, (t, n, name, phone) in CUSTOMERS.items()
    }
    fleet = _fleet()

    def moto(owner, readings, **data):
        """Registra la moto con su primera lectura y las siguientes; cada lectura va (días atrás, km, nota)."""
        (back, km, _), *later = readings
        m = register_motorcycle(user=diana, owner=owner, mileage=km, **data)
        _date(m, now - timedelta(days=back))
        for back, km, note in later:
            update_mileage(motorcycle=m, mileage=km, user=diana, note=note)
            _last_reading(m, now - timedelta(days=back))
        return m

    moto(people["jorge"], [(120, 12500, ""), (35, 14100, ""), (3, 15200, "")], plate="XYZ12A", brand="Bajaj",
         model="Boxer CT 100", year=2019, displacement_cc=100, color="Negro")
    moto(people["jorge"], [(200, 48100, ""), (60, 48900, "")], plate="JKL90B", brand="Suzuki", model="GN 125",
         year=2015, displacement_cc=125, color="Rojo", notes="La usa el hijo para ir a la universidad")
    moto(people["ana"], [(1, 8300, "")], plate="ABC34D", brand="Bajaj", model="Pulsar NS 200", year=2022,
         displacement_cc=200, color="Gris")
    sold = moto(people["luis"], [(400, 9000, ""), (90, 20400, ""), (10, 21000, "")], plate="DEF56G", brand="Honda",
                model="CB 125F", year=2021, displacement_cc=125, color="Azul")
    change_owner(motorcycle=sold, new_owner=fleet, user=diana)  # Luis se la vendió a la mensajería
    Ownership.objects.filter(motorcycle=sold, ended_at__isnull=False).update(ended_at=now - timedelta(days=30))
    Ownership.objects.filter(motorcycle=sold, ended_at__isnull=True).update(started_at=now - timedelta(days=30))
    moto(people["luis"], [(5, 5, "")], vin="9F2NKD125T0001234", brand="AKT", model="NKD 125", year=now.year,
         displacement_cc=125, color="Blanco", notes="Nueva, la placa está en trámite")
    moto(fleet, [(15, 31200, ""), (2, 120, "Cambio de tablero")], plate="GHI78H", brand="Yamaha", model="XTZ 150",
         year=2020, displacement_cc=150, color="Negro")


def _date(motorcycle, when):
    """Corre hacia atrás el registro de la moto: su primer dueño y su primera lectura son de ese día."""
    Motorcycle.objects.filter(pk=motorcycle.pk).update(created_at=when, mileage_at=when)
    Ownership.objects.filter(motorcycle=motorcycle).update(started_at=when)
    MileageReading.objects.filter(motorcycle=motorcycle).update(recorded_at=when)


def _last_reading(motorcycle, when):
    reading = motorcycle.mileage_readings.order_by("-id").first()
    MileageReading.objects.filter(pk=reading.pk).update(recorded_at=when)
    Motorcycle.objects.filter(pk=motorcycle.pk).update(mileage_at=when)


def _today(rng, now, users, warehouses, registers, products):
    """Como la ferretería: caja abierta, venta para revisión, inventario del día y pedido; además, las motos."""
    marta, pedro, laura = users["marta.jefe"][0], users["pedro.bodega"][0], users["laura.caja"][0]
    shift = open_shift(register=registers["CAJA1"], user=laura, opening_float=Decimal(150000))
    Shift.objects.filter(pk=shift.pk).update(opened_at=min(now, _at(now, 7, 50)))
    for minutes in (20, 75, 130):
        _sale(rng, products, laura, shift, min(now, _at(now, 8) + timedelta(minutes=minutes)))
    # Venta hecha sin conexión con el precio viejo del aceite: queda para revisión.
    create_sale(
        user=laura, shift=shift, client_uuid=uuid.uuid4(), offline=True, occurred_at=min(now, _at(now, 9, 40)),
        lines=[{"product": products["ACE-20W50"], "quantity": 1, "unit_price": Decimal(30000)}],
        payments=[{"method": "CASH", "amount": Decimal(30000)}],
    )
    _quotes(now, users, products, shift)
    create_adjustment(
        user=pedro, client_uuid=uuid.uuid4(), warehouse=warehouses["PRAL"], reason="DAMAGE",
        note="Dos bombillos llegaron quemados", lines=[{"product": products["BOM-H4"], "quantity": 2, "direction": "OUT"}],
    )
    used, _ = create_adjustment(
        user=pedro, client_uuid=uuid.uuid4(), warehouse=warehouses["PRAL"], reason="INTERNAL_USE",
        note="Grasa para la moto del mensajero del taller", lines=[{"product": products["GRA-CAD"], "quantity": 1, "direction": "OUT"}],
    )
    approve_adjustment(adjustment=used, user=marta)
    count, _ = open_count(user=pedro, client_uuid=uuid.uuid4(), warehouse=warehouses["PRAL"], category=products["ACE-20W50"].category)
    for line in count.lines.select_related("product"):
        level = line.product.stock_levels.get(warehouse=warehouses["PRAL"]).quantity
        record_line(count=count, line=line, user=pedro, quantity=level - 1 if line.product.sku == "ACE-10W40" else level)
    submit_count(count=count)
    approve_count(count=count, user=marta)
    create_transfer(
        user=marta, client_uuid=uuid.uuid4(), origin=warehouses["PRAL"], destination=warehouses["VIT"],
        note="Surtir el mostrador", lines=[
            {"product": products["BOM-H4"], "quantity": 1, "unit": products["BOM-H4"].units.get().unit},
            {"product": products["FIL-P200"], "quantity": 4},
        ],
    )
    create_order(user=users["andres.ventas"][0], client_uuid=uuid.uuid4(), lines=[
        {"product": products["LLA-90-18"], "quantity": 1}, {"product": products["ACE-20W50"], "quantity": 2},
    ])
    _motorcycles(now, users)


PROFILE = Profile(
    products=PRODUCTS, pending=PENDING, restock=RESTOCK,
    warehouses=(("PRAL", "Bodega principal"), ("VIT", "Mostrador del almacén")), business=_business, today=_today,
    users=(*USERS, ("diana.recepcion", "Diana", "Recepción de taller")),
)
