from django.db import migrations

# Copia congelada del catálogo inicial: las migraciones no deben depender de código que cambia.
# Permisos nuevos: añadirlos en permissions_catalog.py y en una migración nueva.
PERMISSIONS = {
    "users.manage": "Gestionar usuarios y roles",
    "catalog.edit": "Crear y editar productos",
    "catalog.edit_prices": "Cambiar precios y costos",
    "inventory.view": "Ver existencias y kardex",
    "inventory.receive": "Registrar entradas a bodega",
    "inventory.adjust": "Aprobar ajustes y bajas de inventario",
    "inventory.count": "Hacer conteos físicos",
    "sales.create": "Crear ventas y cotizaciones",
    "sales.void": "Anular ventas y hacer devoluciones",
    "cash.operate": "Abrir, cobrar y cerrar caja",
    "reports.view": "Ver reportes",
}

ROLES = {
    "Administrador": list(PERMISSIONS),
    "Supervisor": ["inventory.view", "sales.create", "sales.void", "cash.operate", "reports.view"],
    "Jefe de bodega": [
        "catalog.edit", "inventory.view", "inventory.receive",
        "inventory.adjust", "inventory.count", "reports.view",
    ],
    "Auxiliar de bodega": ["inventory.view", "inventory.receive", "inventory.count"],
    "Ventas": ["inventory.view", "sales.create"],
    "Caja": ["sales.create", "cash.operate"],
}


def seed(apps, schema_editor):
    Permission = apps.get_model("accounts", "Permission")
    Role = apps.get_model("accounts", "Role")
    perms = {}
    for code, description in PERMISSIONS.items():
        perms[code], _ = Permission.objects.get_or_create(code=code, defaults={"description": description})
    for name, codes in ROLES.items():
        role, _ = Role.objects.get_or_create(name=name)
        role.permissions.set(perms[c] for c in codes)


class Migration(migrations.Migration):
    dependencies = [("accounts", "0001_initial")]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
