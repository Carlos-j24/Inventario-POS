from django.db import migrations

# Cliente por defecto de la caja (Res. DIAN 165 de 2023, art. 19, parágrafo 1).
FINAL_CONSUMER = {
    "id_type": "13", "id_number": "222222222222", "person_type": "2",
    "name": "Consumidor final", "tax_responsibilities": ["R-99-PN"],
}


def create(apps, schema_editor):
    Customer = apps.get_model("customers", "Customer")
    Customer.objects.get_or_create(
        id_type=FINAL_CONSUMER["id_type"], id_number=FINAL_CONSUMER["id_number"], defaults=FINAL_CONSUMER,
    )


def remove(apps, schema_editor):
    apps.get_model("customers", "Customer").objects.filter(id_number=FINAL_CONSUMER["id_number"]).delete()


class Migration(migrations.Migration):
    dependencies = [("customers", "0001_initial")]

    operations = [migrations.RunPython(create, remove)]
