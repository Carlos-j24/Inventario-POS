from django.db import migrations

CODE = "workshop.receive"
ROLE = "Recepción de taller"


def add(apps, schema_editor):
    # Spec 009, regla 1: recepción del taller con su permiso; cotiza trabajos con sales.create.
    Permission = apps.get_model("accounts", "Permission")
    Role = apps.get_model("accounts", "Role")
    perm, _ = Permission.objects.get_or_create(
        code=CODE, defaults={"description": "Recibir motos y llevar clientes y motos del taller"},
    )
    for role in Role.objects.filter(name="Administrador"):
        role.permissions.add(perm)
    reception, _ = Role.objects.get_or_create(name=ROLE)
    reception.permissions.add(perm, *Permission.objects.filter(code="sales.create"))


def remove(apps, schema_editor):
    apps.get_model("accounts", "Role").objects.filter(name=ROLE).delete()
    apps.get_model("accounts", "Permission").objects.filter(code=CODE).delete()


class Migration(migrations.Migration):
    dependencies = [("accounts", "0005_inventory_transfer_permission")]

    operations = [migrations.RunPython(add, remove)]
