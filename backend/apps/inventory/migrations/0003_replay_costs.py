from django.db import migrations

from apps.inventory.costing import replay_costs


def replay(apps, schema_editor):
    # Antes de la spec 004 las ventas no guardaban costo: se recalcula todo con el promedio
    # ponderado, en el orden en que pasó, y lo asignado después queda marcado cost_estimated.
    replay_costs(apps.get_model("inventory", "StockMovement"), apps.get_model("inventory", "StockLevel"))


class Migration(migrations.Migration):
    dependencies = [("inventory", "0002_average_cost")]

    operations = [migrations.RunPython(replay, migrations.RunPython.noop)]
