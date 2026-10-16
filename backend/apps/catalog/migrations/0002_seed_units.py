from django.db import migrations

UNITS = {
    "und": "Unidad",
    "m": "Metro",
    "cm": "Centímetro",
    "kg": "Kilogramo",
    "lb": "Libra",
    "gal": "Galón",
    "rollo": "Rollo",
    "bulto": "Bulto",
    "caja": "Caja",
    "par": "Par",
}


def seed(apps, schema_editor):
    Unit = apps.get_model("catalog", "Unit")
    for code, name in UNITS.items():
        Unit.objects.get_or_create(code=code, defaults={"name": name})


class Migration(migrations.Migration):
    dependencies = [("catalog", "0001_initial")]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
