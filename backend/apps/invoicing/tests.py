import datetime
import threading

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from rest_framework.test import APIClient

from apps.cash.models import CashRegister

from .models import NumberingResolution, two_years_after
from .numbering import NumberingError, resolution_status, take_number

pytestmark = pytest.mark.django_db

TODAY = datetime.date(2026, 10, 17)
POS = NumberingResolution.DocumentType.POS


def resolution(register, **over):
    data = {
        "register": register, "document_type": POS, "number": "18764000000001", "issued_on": datetime.date(2026, 1, 10),
        "valid_from": datetime.date(2026, 1, 10), "valid_until": datetime.date(2027, 1, 10),
        "prefix": "CJ1", "range_from": 1, "range_to": 1000, **over,
    }
    return NumberingResolution.objects.create(**data)


# --- consecutivos ------------------------------------------------------------

def test_numbers_are_consecutive_with_prefix_and_no_leading_zeros(register):
    res = resolution(register)
    taken = [take_number(register, POS, TODAY) for _ in range(3)]
    assert [n for _, n in taken] == [1, 2, 3]
    assert taken[0][0].format(7) == "CJ17"
    res.refresh_from_db()
    assert (res.next_number, res.remaining) == (4, 997)


def test_a_rolled_back_document_does_not_spend_its_number(register):
    resolution(register)
    with pytest.raises(RuntimeError), transaction.atomic():
        take_number(register, POS, TODAY)
        raise RuntimeError("la venta falló")
    assert take_number(register, POS, TODAY)[1] == 1


def test_when_one_runs_out_the_next_resolution_continues(register):
    old = resolution(register, range_from=1, range_to=2)
    new = resolution(register, number="2", prefix="CJ1", range_from=3, range_to=10, valid_from=datetime.date(2026, 6, 1))
    assert [take_number(register, POS, TODAY)[0].pk for _ in range(3)] == [old.pk, old.pk, new.pk]


def test_the_oldest_resolution_is_used_first(register):
    resolution(register, prefix="B", valid_from=datetime.date(2026, 6, 1))  # creada antes, pero rige después
    earlier = resolution(register, prefix="A", valid_from=datetime.date(2026, 2, 1))
    assert take_number(register, POS, TODAY)[0].pk == earlier.pk


def test_only_this_register_type_and_active_resolutions(register, warehouse):
    other = CashRegister.objects.create(code="CAJA2", name="Caja 2", warehouse=warehouse)
    resolution(other, prefix="CJ2")
    resolution(register, document_type=NumberingResolution.DocumentType.INVOICE, prefix="FE1")
    resolution(register, prefix="OFF", is_active=False)
    with pytest.raises(NumberingError, match="no tiene resolución"):
        take_number(register, POS, TODAY)


@pytest.mark.parametrize("over, message", [
    ({"range_to": 1, "next_number": 2}, "se agotó"),
    ({"valid_until": datetime.date(2026, 10, 16)}, "venció el 16/10/2026"),
    ({"valid_from": datetime.date(2026, 10, 18)}, "empieza a regir el 18/10/2026"),
])
def test_no_number_explains_why(register, over, message):
    resolution(register, **over)
    with pytest.raises(NumberingError, match=message):
        take_number(register, POS, TODAY)


def test_the_last_day_of_validity_still_works(register):
    resolution(register, valid_from=TODAY, valid_until=TODAY)
    assert take_number(register, POS, TODAY)[1] == 1


@pytest.mark.skipif(connection.vendor == "sqlite", reason="SQLite no permite escrituras concurrentes")
@pytest.mark.django_db(transaction=True)
def test_two_registers_at_once_never_repeat_a_number(register):  # pragma: no cover
    resolution(register, range_to=40)
    numbers, errors = [], []

    def sell():
        try:
            for _ in range(10):
                with transaction.atomic():
                    numbers.append(take_number(register, POS, TODAY)[1])
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=sell) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert sorted(numbers) == list(range(1, 31))


# --- avisos ----------------------------------------------------------------

@pytest.mark.parametrize("size, remaining, warned", [
    (1000, 100, True), (1000, 101, False),  # el umbral es 100 números…
    (5000, 500, True), (5000, 501, False),  # …o el 10 % del rango si es mayor
])
def test_low_numbers_warning(register, size, remaining, warned):
    res = resolution(register, range_to=size, next_number=size - remaining + 1)
    status = resolution_status(res, TODAY)
    assert status["remaining"] == remaining
    assert (f"Quedan {remaining} números." in status["warnings"]) is warned


@pytest.mark.parametrize("valid_until, warning", [
    (TODAY + datetime.timedelta(days=31), None),
    (TODAY + datetime.timedelta(days=30), "Vence en 30 días."),
    (TODAY, "Vence hoy."),
])
def test_expiry_warning(register, valid_until, warning):
    status = resolution_status(resolution(register, valid_until=valid_until), TODAY)
    assert (status["state"], status["warnings"]) == ("current", [warning] if warning else [])


@pytest.mark.parametrize("over, state, warnings", [
    ({"valid_until": datetime.date(2026, 10, 1)}, "expired", ["Venció el 01/10/2026."]),
    ({"valid_until": datetime.date(2026, 10, 16)}, "expired", ["Venció el 16/10/2026."]),  # ayer
    ({"range_to": 5, "next_number": 6}, "exhausted", ["Se agotaron los números."]),
    ({"valid_from": datetime.date(2026, 11, 1)}, "upcoming", []),
])
def test_resolution_states(register, over, state, warnings):
    status = resolution_status(resolution(register, **over), TODAY)
    assert (status["state"], status["warnings"]) == (state, warnings)


# --- validaciones ------------------------------------------------------------

def test_validity_is_at_most_two_years(register):
    res = NumberingResolution(
        register=register, document_type=POS, number="1", issued_on=datetime.date(2026, 1, 10),
        valid_from=datetime.date(2026, 1, 10), valid_until=datetime.date(2028, 1, 10), prefix="X", range_from=1, range_to=10,
    )
    res.full_clean(exclude=["next_number"])
    res.valid_until = datetime.date(2028, 1, 11)
    with pytest.raises(ValidationError, match="máximo dos años"):
        res.full_clean(exclude=["next_number"])
    assert two_years_after(datetime.date(2028, 2, 29)) == datetime.date(2030, 2, 28)


def test_ranges_of_the_same_prefix_cannot_overlap(register, warehouse):
    resolution(register, range_from=1, range_to=100)
    other = CashRegister.objects.create(code="CAJA2", name="Caja 2", warehouse=warehouse)

    def candidate(**over):
        data = {"register": other, "document_type": POS, "number": "9", "issued_on": TODAY, "valid_from": TODAY,
                "valid_until": TODAY, "prefix": "CJ1", "range_from": 100, "range_to": 200, **over}
        return NumberingResolution(**data)

    with pytest.raises(ValidationError, match="se cruza"):
        candidate().full_clean(exclude=["next_number"])
    candidate(range_from=101).full_clean(exclude=["next_number"])  # contiguo: bien
    candidate(prefix="CJ2").full_clean(exclude=["next_number"])  # otro prefijo
    candidate(document_type=NumberingResolution.DocumentType.INVOICE).full_clean(exclude=["next_number"])
    with pytest.raises(ValidationError, match="termina antes"):
        candidate(range_from=300, range_to=299).full_clean(exclude=["next_number"])


@pytest.mark.parametrize("over", [
    {"next_number": 1002},  # más allá del rango
    {"range_from": 0},
    {"valid_from": datetime.date(2026, 1, 9)},  # antes de la resolución
])
def test_database_constraints(register, over):
    with transaction.atomic(), pytest.raises(IntegrityError):
        resolution(register, **over)


# --- API ---------------------------------------------------------------------

def test_api_lists_active_resolutions_with_status(register, make_user, warehouse):
    resolution(register, range_to=1000, next_number=950)
    resolution(register, prefix="OLD", is_active=False)
    other = CashRegister.objects.create(code="CAJA2", name="Caja 2", warehouse=warehouse)
    resolution(other, prefix="CJ2")
    client = APIClient()
    client.force_authenticate(make_user("caja", "Caja"))
    rows = client.get("/api/invoicing/numbering/", {"register": register.pk}).data
    assert len(rows) == 1
    assert (rows[0]["register"], rows[0]["prefix"], rows[0]["remaining"]) == ("CAJA1", "CJ1", 51)
    assert "Quedan 51 números." in rows[0]["status"]["warnings"]
    assert len(client.get("/api/invoicing/numbering/").data) == 2
    client.force_authenticate(make_user("bodega", "Auxiliar de bodega"))
    assert client.get("/api/invoicing/numbering/").status_code == 403
