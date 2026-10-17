from django.db import migrations

CODE = "reports.costs"


def add(apps, schema_editor):
    # Spec 004, decisión 4: costos y márgenes solo para el Administrador por defecto.
    Permission = apps.get_model("accounts", "Permission")
    Role = apps.get_model("accounts", "Role")
    perm, _ = Permission.objects.get_or_create(code=CODE, defaults={"description": "Ver costos y márgenes"})
    admin = Role.objects.filter(name="Administrador").first()
    if admin:
        admin.permissions.add(perm)


def remove(apps, schema_editor):
    apps.get_model("accounts", "Permission").objects.filter(code=CODE).delete()


class Migration(migrations.Migration):
    dependencies = [("accounts", "0003_must_change_password")]

    operations = [migrations.RunPython(add, remove)]
