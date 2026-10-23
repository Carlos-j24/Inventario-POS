# Spec 008: bodega principal (la que proponen las pantallas de inventario).

from django.db import migrations, models


def mark_default(apps, schema_editor):
    """La principal es PRAL si existe y está activa; si no, la primera activa por código."""
    Warehouse = apps.get_model("inventory", "Warehouse")
    active = Warehouse.objects.filter(is_active=True)
    chosen = active.filter(code="PRAL").first() or active.order_by("code").first()
    if chosen:
        Warehouse.objects.filter(pk=chosen.pk).update(is_default=True)


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0006_transfers'),
    ]

    operations = [
        migrations.AddField(
            model_name='warehouse',
            name='is_default',
            field=models.BooleanField(default=False, help_text='La que proponen las pantallas de inventario (spec 008). Solo una; marcar otra desmarca esta.', verbose_name='principal'),
        ),
        migrations.RunPython(mark_default, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='warehouse',
            constraint=models.UniqueConstraint(condition=models.Q(('is_default', True)), fields=('is_default',), name='one_default_warehouse'),
        ),
        migrations.AddConstraint(
            model_name='warehouse',
            constraint=models.CheckConstraint(condition=models.Q(('is_default', False), ('is_active', True), _connector='OR'), name='default_warehouse_is_active'),
        ),
    ]
