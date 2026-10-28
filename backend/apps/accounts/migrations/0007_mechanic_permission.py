from django.db import migrations

CODE = "workshop.repair"
ROLE = "Mecánico"


def add(apps, schema_editor):
    # Spec 011, regla 6: el mecánico lleva sus órdenes de trabajo; el administrador también puede.
    Permission = apps.get_model("accounts", "Permission")
    Role = apps.get_model("accounts", "Role")
    perm, _ = Permission.objects.get_or_create(
        code=CODE, defaults={"description": "Diagnosticar y reparar motos de sus órdenes de trabajo"},
    )
    for role in Role.objects.filter(name="Administrador"):
        role.permissions.add(perm)
    mechanic, _ = Role.objects.get_or_create(name=ROLE)
    mechanic.permissions.add(perm)


def remove(apps, schema_editor):
    apps.get_model("accounts", "Role").objects.filter(name=ROLE).delete()
    apps.get_model("accounts", "Permission").objects.filter(code=CODE).delete()


class Migration(migrations.Migration):
    dependencies = [("accounts", "0006_workshop_permission")]

    operations = [migrations.RunPython(add, remove)]
