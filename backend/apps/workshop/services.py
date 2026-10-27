"""Motos y sus dueños (spec 009, T1).

Reglas:
- El dueño es el mismo `Customer` de la caja (decisión 2); desde el taller, además, con teléfono.
  El consumidor final no puede ser dueño de una moto.
- Registrar una moto abre su primer registro de dueño; cambiar de dueño cierra el anterior y abre
  otro en una transacción (decisión 4). `Motorcycle.owner` siempre es el del registro abierto.
- El kilometraje solo sube; bajarlo exige una nota (regla 5). Cada lectura queda guardada.
"""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import MileageReading, Motorcycle, Ownership


def check_owner(customer):
    """Un cliente puede ser dueño si está activo, tiene teléfono y no es el consumidor final."""
    if customer.is_final_consumer:
        raise ValidationError({"owner": "El consumidor final no puede ser dueño de una moto: registra al cliente."})
    if not customer.is_active:
        raise ValidationError({"owner": "El cliente está inactivo."})
    if not customer.phone.strip():
        raise ValidationError({"owner": "El cliente necesita un teléfono para avisarle cuando la moto esté lista."})


@transaction.atomic
def register_motorcycle(*, user, owner, mileage=0, **data):
    """Registra una moto con su dueño y, si se da, su primer kilometraje. Devuelve la moto."""
    check_owner(owner)
    now = timezone.now()
    motorcycle = Motorcycle(owner=owner, mileage=mileage, mileage_at=now if mileage else None, **data)
    motorcycle.full_clean()
    motorcycle.save()
    Ownership.objects.create(motorcycle=motorcycle, customer=owner, started_at=now, created_by=user)
    if mileage:
        MileageReading.objects.create(motorcycle=motorcycle, mileage=mileage, recorded_at=now, recorded_by=user)
    return motorcycle


@transaction.atomic
def change_owner(*, motorcycle, new_owner, user):
    """Pasa la moto a otro cliente: cierra el registro del dueño actual y abre el del nuevo."""
    motorcycle = Motorcycle.objects.select_for_update().get(pk=motorcycle.pk)
    if new_owner.pk == motorcycle.owner_id:
        raise ValidationError({"owner": "Ese cliente ya es el dueño de la moto."})
    check_owner(new_owner)
    now = timezone.now()
    Ownership.objects.filter(motorcycle=motorcycle, ended_at__isnull=True).update(ended_at=now)
    Ownership.objects.create(motorcycle=motorcycle, customer=new_owner, started_at=now, created_by=user)
    motorcycle.owner = new_owner
    motorcycle.save(update_fields=["owner", "updated_at"])
    return motorcycle


@transaction.atomic
def update_mileage(*, motorcycle, mileage, user, note=""):
    """Guarda una lectura del kilometraje. Para bajarlo hace falta una nota que lo explique."""
    motorcycle = Motorcycle.objects.select_for_update().get(pk=motorcycle.pk)
    note = note.strip()
    if mileage < 0:
        raise ValidationError({"mileage": "El kilometraje no puede ser negativo."})
    if mileage < motorcycle.mileage and not note:
        raise ValidationError({
            "mileage": f"El kilometraje solo sube (va en {motorcycle.mileage} km). "
                       "Si cambiaron el tablero o hubo un error, escribe una nota.",
        })
    now = timezone.now()
    MileageReading.objects.create(
        motorcycle=motorcycle, mileage=mileage, previous=motorcycle.mileage, note=note, recorded_at=now, recorded_by=user,
    )
    motorcycle.mileage, motorcycle.mileage_at = mileage, now
    motorcycle.save(update_fields=["mileage", "mileage_at", "updated_at"])
    return motorcycle
