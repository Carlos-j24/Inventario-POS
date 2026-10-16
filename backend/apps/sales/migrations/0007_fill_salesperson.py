from django.db import migrations
from django.db.models import F


def fill(apps, schema_editor):
    # Antes de la spec 002 toda venta era directa en caja: quien la vendió es quien la cobró.
    Sale = apps.get_model("sales", "Sale")
    Sale.objects.filter(salesperson__isnull=True).update(salesperson=F("seller"))


class Migration(migrations.Migration):
    dependencies = [("sales", "0006_orders_and_salesperson")]

    operations = [migrations.RunPython(fill, migrations.RunPython.noop)]
