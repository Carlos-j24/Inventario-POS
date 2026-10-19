from django.db import migrations

CODE = "inventory.transfer"
ROLES = ["Administrador", "Jefe de bodega", "Auxiliar de bodega"]


def add(apps, schema_editor):
    # Spec 006, decisión 5: mover mercancía entre bodegas es un permiso propio.
    Permission = apps.get_model("accounts", "Permission")
    Role = apps.get_model("accounts", "Role")
    perm, _ = Permission.objects.get_or_create(code=CODE, defaults={"description": "Trasladar mercancía entre bodegas"})
    for role in Role.objects.filter(name__in=ROLES):
        role.permissions.add(perm)


def remove(apps, schema_editor):
    apps.get_model("accounts", "Permission").objects.filter(code=CODE).delete()


class Migration(migrations.Migration):
    dependencies = [("accounts", "0004_reports_costs_permission")]

    operations = [migrations.RunPython(add, remove)]
