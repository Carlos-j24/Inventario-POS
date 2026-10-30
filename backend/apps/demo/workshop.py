"""Demo de un taller de motos con repuestos (spec 009, T4): `seed_demo --taller`.

La misma historia que la ferretería (turnos, anulación, devolución, faltante, venta para revisión,
conteo, traslado, pedido y cotizaciones) con repuestos de moto, más el módulo de taller activo,
una recepcionista y clientes con sus motos: una con dueño anterior, una sin placa y lecturas de
kilometraje de los últimos meses. Los datos del negocio son ficticios.

Lavadero (spec 010): lavados todos los días, alguno con un repuesto, y hoy uno cobrado sin conexión.

Órdenes de trabajo (spec 011, T7): un mecánico, la mano de obra de taller y una orden en cada estado,
hechas con los mismos servicios que usa la app: una en reparación con un cambio sin aprobar, una lista
en la caja sin cobrar, una entregada y cobrada, y una cancelada con su repuesto devuelto a la bodega.

Mantenimientos (spec 012, T6): tres planes y visitas de meses atrás, entregadas con los mismos servicios,
que dejan un recordatorio en cada estado: uno vencido por fecha, uno que vence por km estimados, uno
avisado por WhatsApp, uno hecho con la orden de hoy y uno descartado. Esas visitas se cobran en el turno
de hoy, para no tocar los cierres de los días pasados.
"""
import random
import uuid
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from apps.cash.models import Shift
from apps.cash.services import open_shift
from apps.catalog.models import Product, Unit
from apps.customers.models import Customer
from apps.customers.rules import check_digit
from apps.inventory.adjustments import approve_adjustment, create_adjustment
from apps.inventory.counts import approve_count, open_count, record_line, submit_count
from apps.inventory.transfers import create_transfer
from apps.invoicing.models import Business
from apps.sales.models import Quote, Sale
from apps.sales.orders import create_order
from apps.sales.quotes import convert_quote, create_quote, void_quote
from apps.sales.services import catalog_price, create_sale, money
from apps.workshop import maintenance
from apps.workshop import work_orders as wo
from apps.workshop.models import (
    MaintenanceNotice, MaintenancePlan, MaintenanceReminder, MileageReading, Motorcycle, Ownership, WorkOrder,
    WorkOrderEvent,
)
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
SERVICES = (
    ("LAV-150", "Lavado moto hasta 150 cc", "Lavadero", 12000),
    ("LAV-AC", "Lavado moto alto cilindraje", "Lavadero", 18000),
    ("LAV-MOT", "Lavado de motor y desengrase", "Lavadero", 15000),
    # Precio de referencia: recepción pone el de cada trabajo (spec 011).
    ("MO-TALLER", "Mano de obra de taller", "Taller", 20000),
)
MECHANIC = ("jhon.mecanico", "Jhon", "Mecánico")
# Planes de mantenimiento (spec 012): nombre, cada cuántos km, cada cuántos días y los productos que lo cumplen.
PLANS = (
    ("Cambio de aceite", 3000, 90, ("ACE-20W50", "ACE-10W40")),
    ("Revisión de frenos", 5000, 180, ("PAS-DEL", "BAN-TRA")),
    ("Kit de arrastre", 15000, None, ("KIT-BOX100", "CAD-428")),
)

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


def _motorcycles(now, users, products, shift):
    """Motos de ejemplo con su historia: lecturas de meses atrás, una vendida a otro dueño y una sin placa.

    Algunas pasaron por el taller en una de esas lecturas (spec 012): de ahí salen sus recordatorios.
    """
    diana = users["diana.recepcion"][0]
    people = {
        key: Customer.objects.create(id_type=t, id_number=n, name=name, phone=phone, check_digit="")
        for key, (t, n, name, phone) in CUSTOMERS.items()
    }
    fleet = _fleet()

    def moto(owner, readings, visit=None, **data):
        """Registra la moto con su primera lectura y las siguientes; cada lectura va (días atrás, km, nota).

        `visit` es (días atrás, lo que pidió, diagnóstico, repuestos): ese día la entregaron del taller.
        """
        (back, km, _), *later = readings
        m = register_motorcycle(user=diana, owner=owner, mileage=km, **data)
        _date(m, now - timedelta(days=back))
        for back, km, note in [(back, None, ""), *later]:
            if km is not None:
                m = update_mileage(motorcycle=m, mileage=km, user=diana, note=note)
                _last_reading(m, now - timedelta(days=back))
            if visit and visit[0] == back:
                _past_visit(m, now - timedelta(days=back), *visit[1:], users=users, products=products, shift=shift)
        return m

    moto(people["jorge"], [(120, 12500, ""), (35, 14100, ""), (3, 15200, "")], plate="XYZ12A", brand="Bajaj",
         model="Boxer CT 100", year=2019, displacement_cc=100, color="Negro",
         visit=(120, "Cambio de aceite", "Aceite negro", [("ACE-20W50", 1)]))
    moto(people["jorge"], [(200, 48100, ""), (100, 48500, ""), (60, 48900, "")], plate="JKL90B", brand="Suzuki",
         model="GN 125", year=2015, displacement_cc=125, color="Rojo", notes="La usa el hijo para ir a la universidad",
         visit=(100, "Cambio de aceite", "Le tocaba", [("ACE-20W50", 1)]))
    moto(people["ana"], [(55, 5600, ""), (20, 7400, ""), (1, 8300, "")], plate="ABC34D", brand="Bajaj",
         model="Pulsar NS 200", year=2022, displacement_cc=200, color="Gris",
         visit=(55, "Primer cambio de aceite sintético", "Sin novedades", [("ACE-10W40", 1)]))
    sold = moto(people["luis"], [(400, 9000, ""), (90, 20400, ""), (10, 21000, "")], plate="DEF56G", brand="Honda",
                model="CB 125F", year=2021, displacement_cc=125, color="Azul",
                visit=(90, "Cambio de aceite y cadena", "Cadena estirada", [("ACE-20W50", 1), ("CAD-428", 1)]))
    change_owner(motorcycle=sold, new_owner=fleet, user=diana)  # Luis se la vendió a la mensajería
    Ownership.objects.filter(motorcycle=sold, ended_at__isnull=False).update(ended_at=now - timedelta(days=30))
    Ownership.objects.filter(motorcycle=sold, ended_at__isnull=True).update(started_at=now - timedelta(days=30))
    moto(people["luis"], [(5, 5, "")], vin="9F2NKD125T0001234", brand="AKT", model="NKD 125", year=now.year,
         displacement_cc=125, color="Blanco", notes="Nueva, la placa está en trámite")
    moto(fleet, [(15, 31200, ""), (2, 120, "Cambio de tablero")], plate="GHI78H", brand="Yamaha", model="XTZ 150",
         year=2020, displacement_cc=150, color="Negro")


def _charge(cashier, shift, lines, when, offline=False):
    """Cobra en efectivo, al precio del catálogo, con la hora del día de la historia."""
    total = sum(money(catalog_price(line["product"], line["product"].base_unit) * line["quantity"]) for line in lines)
    sale, _ = create_sale(user=cashier, shift=shift, client_uuid=uuid.uuid4(), lines=lines, offline=offline,
                          occurred_at=when, payments=[{"method": "CASH", "amount": total}])
    Sale.objects.filter(pk=sale.pk).update(created_at=when)
    return sale


def _washes(day, shift, cashier, products):
    """De 2 a 4 lavados al día; el primero, con grasa para la cadena si alcanza el stock.

    Con su propio azar (por fecha), para no cambiar las ventas al azar del resto de la historia.
    """
    rng = random.Random(day.toordinal())
    washes = {p.sku: p for p in Product.objects.filter(is_service=True)}
    grease = products["GRA-CAD"]
    for n in range(rng.randint(2, 4)):
        lines = [{"product": washes[rng.choice(["LAV-150", "LAV-150", "LAV-AC", "LAV-MOT"])], "quantity": 1}]
        if n == 0 and grease.stock_levels.get(warehouse=shift.register.warehouse).quantity - 1 >= grease.min_stock:
            lines.append({"product": grease, "quantity": 1})
        _charge(cashier, shift, lines, _at(day, 9 + 2 * n, rng.randint(0, 59)))


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
    # Lavadero (spec 010): un lavado con cambio de aceite y otro cobrado sin conexión, que no queda para revisión.
    washes = {p.sku: p for p in Product.objects.filter(is_service=True)}
    _charge(laura, shift, [{"product": washes["LAV-150"], "quantity": 1}, {"product": products["ACE-20W50"], "quantity": 1}],
            min(now, _at(now, 8, 45)))
    _charge(laura, shift, [{"product": washes["LAV-AC"], "quantity": 1}], min(now, _at(now, 9, 10)), offline=True)
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
    _plans(products)
    _motorcycles(now, users, products, shift)
    _maintenance(now, users)
    _work_orders(now, users, products, shift)


def _plans(products):
    for name, every_km, every_days, skus in PLANS:
        plan = MaintenancePlan.objects.create(name=name, every_km=every_km, every_days=every_days)
        plan.products.set(products[sku] for sku in skus)


def _budget(order, users, products, diagnosis, parts, work_price):
    """El mecánico diagnostica y agrega los repuestos; recepción agrega la mano de obra con su precio."""
    diana, jhon = users["diana.recepcion"][0], users[MECHANIC[0]][0]
    wo.diagnose(order=order, user=jhon, diagnosis=diagnosis)
    for sku, qty in parts:
        wo.add_line(order=order, user=jhon, product=products[sku], quantity=qty)
    wo.add_line(order=order, user=diana, product=Product.objects.get(sku="MO-TALLER"), quantity=1,
                unit_price=Decimal(work_price))


def _repaired(order, users, approved_by, channel="PHONE"):
    """Aprobada y con todos sus repuestos puestos."""
    wo.approve(order=order, user=users["diana.recepcion"][0], approved_by=approved_by, channel=channel)
    for line in order.lines.filter(is_service=False, movement__isnull=True):
        wo.take_part(line=line, user=users[MECHANIC[0]][0])


def _paid(order, users, shift):
    """Lista, en la caja y cobrada en efectivo."""
    wo.mark_ready(order=order, user=users[MECHANIC[0]][0])
    till = wo.send_to_till(order=order, user=users["diana.recepcion"][0])
    create_sale(user=users["laura.caja"][0], shift=shift, order=till, lines=None, client_uuid=uuid.uuid4(),
                payments=[{"method": "CASH", "amount": till.total}])


def _back(order, when):
    """La orden y todos sus pasos quedan con la fecha en que llegó la moto."""
    WorkOrder.objects.filter(pk=order.pk).update(received_at=when)
    WorkOrderEvent.objects.filter(work_order=order).update(at=when)


def _past_visit(motorcycle, when, request, diagnosis, parts, *, users, products, shift):
    """Una visita de hace tiempo, entregada ese día: sus recordatorios vencen contando desde entonces."""
    diana = users["diana.recepcion"][0]
    order = wo.receive_order(user=diana, motorcycle=motorcycle, mileage=motorcycle.mileage, request=request,
                             mechanic=users[MECHANIC[0]][0])
    _budget(order, users, products, diagnosis, parts, 15000)
    _repaired(order, users, motorcycle.owner.name)
    _paid(order, users, shift)
    wo.deliver(order=order, user=diana)
    _back(order, when)
    for reminder in order.reminders_created.select_related("plan"):
        if reminder.due_date:
            reminder.due_date = timezone.localdate(when) + timedelta(days=reminder.plan.every_days)
        reminder.created_at = when
        reminder.save(update_fields=["due_date", "created_at"])
    return order


def _maintenance(now, users):
    """Recepción avisó por WhatsApp a Jorge del aceite de la Boxer, y la mensajería no quiere el aviso del kit."""
    diana = users["diana.recepcion"][0]
    boxer = MaintenanceReminder.objects.get(motorcycle__plate="XYZ12A", plan__name="Cambio de aceite")
    maintenance.notify(reminder=boxer, user=diana, channel="WHATSAPP")
    MaintenanceNotice.objects.filter(reminder=boxer).update(at=now - timedelta(days=28))
    kit = MaintenanceReminder.objects.get(motorcycle__plate="DEF56G", plan__name="Kit de arrastre")
    maintenance.dismiss(reminder=kit, user=diana, note="La mensajería le cambia el kit con su propio mecánico")
    MaintenanceReminder.objects.filter(pk=kit.pk).update(closed_at=now - timedelta(days=25))


def _work_orders(now, users, products, shift):
    """Una orden en cada estado, con la historia que tendría en la app (spec 011, regla 13)."""
    diana, jhon = users["diana.recepcion"][0], users[MECHANIC[0]][0]
    motos = {m.plate or m.vin: m for m in Motorcycle.objects.all()}

    def receive(plate, mileage, request, condition="", mechanic=jhon, back=0):
        order = wo.receive_order(user=diana, motorcycle=motos[plate], mileage=mileage, request=request,
                                 condition=condition, mechanic=mechanic)
        if back:  # llegó hace unos días
            _back(order, now - timedelta(days=back))
            order.refresh_from_db()
        return order

    def budget(order, diagnosis, parts, work_price):
        _budget(order, users, products, diagnosis, parts, work_price)

    def repaired(order, approved_by, channel="PHONE"):
        _repaired(order, users, approved_by, channel)

    # Entregada y cobrada: la flota trajo la Honda hace dos días. Cumple el aceite de su visita anterior.
    honda = receive("DEF56G", 21050, "Mantenimiento de los 21.000 km", "Sin espejo izquierdo", back=2)
    budget(honda, "Cambio de aceite y bujía", [("ACE-20W50", 1), ("BUJ-C7", 1)], 25000)
    repaired(honda, "Jefe de flota de la mensajería")
    _paid(honda, users, shift)
    wo.deliver(order=honda, user=diana, mileage=21052)

    # Cancelada: el repuesto ya había salido y volvió a la bodega.
    suzuki = receive("JKL90B", 49000, "No prende", "Batería descargada", back=1)
    budget(suzuki, "Bujía dañada", [("BUJ-C7", 1)], 10000)
    repaired(suzuki, "Jorge Ramírez")
    wo.cancel(order=suzuki, user=diana, reason="El cliente se la llevó sin arreglar")

    # Lista y en la caja, sin cobrar todavía.
    yamaha = receive("GHI78H", 150, "Ajustar y lubricar la cadena")
    budget(yamaha, "Cadena seca y floja", [("GRA-CAD", 1)], 15000)
    repaired(yamaha, "Jefe de flota de la mensajería", "IN_PERSON")
    wo.mark_ready(order=yamaha, user=jhon)
    wo.send_to_till(order=yamaha, user=diana)

    # En reparación, con un cambio que el cliente todavía no aprueba (el caso de la spec).
    boxer = receive("XYZ12A", 15400, "Cambio de aceite y revisar frenos", "Rayón en el tanque, deja el casco")
    budget(boxer, "Aceite vencido y pastillas gastadas", [("ACE-20W50", 1), ("PAS-DEL", 1)], 25000)
    repaired(boxer, "Jorge Ramírez")
    wo.add_line(order=boxer, user=jhon, product=products["BAN-TRA"], quantity=1)

    # Esperando aprobación.
    pulsar = receive("ABC34D", 8350, "Suena el motor", "Sin novedades")
    budget(pulsar, "Cadenilla del árbol de levas floja", [("FIL-P200", 1)], 60000)
    wo.send_for_approval(order=pulsar, user=jhon)

    # Recibida, sin mecánico todavía.
    receive("9F2NKD125T0001234", 40, "Primera revisión", "Nueva, sin placa", mechanic=None)


PROFILE = Profile(
    products=PRODUCTS, pending=PENDING, restock=RESTOCK,
    warehouses=(("PRAL", "Bodega principal"), ("VIT", "Mostrador del almacén")), business=_business, today=_today,
    users=(*USERS, ("diana.recepcion", "Diana", "Recepción de taller"), MECHANIC),
    services=SERVICES, daily=_washes,
)
