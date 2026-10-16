# Inventario-POS

Inventario y punto de venta para ferreterías (después supermercados y droguerías): entradas a bodega, ventas que descuentan stock, caja y usuarios con roles. Web con modo sin conexión.

## Arrancar el backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\python manage.py migrate
.venv\Scripts\python manage.py createsuperuser
.venv\Scripts\python manage.py runserver
```

Admin en http://127.0.0.1:8000/admin/. Tests: `.venv\Scripts\python -m pytest`.

## Documentación
- [Arquitectura](docs/arquitectura.md) · [Constitución](docs/constitution.md)
- [Spec 001 — MVP](specs/001-mvp/spec.md) y sus [tareas](specs/001-mvp/tasks.md)
- Reglas para agentes de IA: [AGENTS.md](AGENTS.md)
