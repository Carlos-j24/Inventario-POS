"""Fixtures de facturación electrónica compartidas por los tests de la app."""
import datetime

import pytest

from apps.customers.models import Customer
from apps.inventory.models import StockMovement
from apps.inventory.services import record_movement

from .models import NumberingResolution


@pytest.fixture
def cashier(make_user):
    return make_user("caja1", "Caja")


@pytest.fixture
def stocked(cashier, warehouse, hammer, cable):
    for product, qty in ((hammer, 20), (cable, 500)):
        record_movement(kind=StockMovement.Kind.RECEIPT, product=product, warehouse=warehouse, quantity=qty, user=cashier, unit_cost="1000")


@pytest.fixture
def numbering(register):
    common = {"register": register, "number": "18764", "issued_on": datetime.date(2026, 1, 1),
              "valid_from": datetime.date(2026, 1, 1), "valid_until": datetime.date(2027, 12, 31), "range_from": 1, "range_to": 5000}
    NumberingResolution.objects.create(document_type="POS", prefix="CJ1", **common)
    NumberingResolution.objects.create(document_type="INVOICE", prefix="FE1", **common)


@pytest.fixture
def contingency(register):
    return NumberingResolution.objects.create(
        register=register, document_type="CONTINGENCY", number="18765", issued_on=datetime.date(2026, 1, 1),
        valid_from=datetime.date(2026, 1, 1), valid_until=datetime.date(2027, 12, 31), prefix="CT1", range_from=1, range_to=1000,
    )


@pytest.fixture
def client_co(db):
    return Customer.objects.create(id_type="31", id_number="800197268", check_digit="4", person_type="1", name="Constructora SAS", email="compras@ejemplo.co")
