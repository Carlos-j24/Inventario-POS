from django.db import migrations

# Consecutivos internos de las notas: se crean aquí para que nunca haya carrera al crearlos.
KEYS = ["POS_ADJUSTMENT", "CREDIT_NOTE"]


def create(apps, schema_editor):
    Counter = apps.get_model("invoicing", "InternalCounter")
    for key in KEYS:
        Counter.objects.get_or_create(key=key)


def remove(apps, schema_editor):
    apps.get_model("invoicing", "InternalCounter").objects.filter(key__in=KEYS).delete()


class Migration(migrations.Migration):
    dependencies = [("invoicing", "0002_fiscal_documents")]

    operations = [migrations.RunPython(create, remove)]
