from django.db import migrations

CODE = "expenses.manage"


def add(apps, schema_editor):
    # Spec 013, decisión 8: anotar, corregir y anular gastos; de entrada, solo el administrador.
    Permission = apps.get_model("accounts", "Permission")
    Role = apps.get_model("accounts", "Role")
    perm, _ = Permission.objects.get_or_create(
        code=CODE, defaults={"description": "Anotar, corregir y anular los gastos del negocio"},
    )
    for role in Role.objects.filter(name="Administrador"):
        role.permissions.add(perm)


def remove(apps, schema_editor):
    apps.get_model("accounts", "Permission").objects.filter(code=CODE).delete()


class Migration(migrations.Migration):
    dependencies = [("accounts", "0007_mechanic_permission")]

    operations = [migrations.RunPython(add, remove)]
