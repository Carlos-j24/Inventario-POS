from django.db import migrations

# Una lista corta para empezar (spec 013, regla 7); el administrador la cambia en la pantalla Gastos.
NAMES = ["Arriendo", "Sueldos", "Servicios públicos", "Insumos", "Otros"]


def add(apps, schema_editor):
    Category = apps.get_model("expenses", "ExpenseCategory")
    for name in NAMES:
        Category.objects.get_or_create(name=name)


def remove(apps, schema_editor):
    apps.get_model("expenses", "ExpenseCategory").objects.filter(name__in=NAMES, expenses__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [("expenses", "0001_initial")]

    operations = [migrations.RunPython(add, remove)]
