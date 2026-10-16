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

Antes de vender, crea en el admin al menos una **bodega** y una **caja** (Caja → Cajas), y asigna roles a los usuarios.

## Arrancar el frontend (PWA)

Con el backend corriendo en el puerto 8000:

```bash
cd frontend
npm install
npm run dev
```

Abre http://localhost:5173. Vite reenvía `/api` a Django, así que el navegador ve un solo dominio (necesario para la sesión en cookie). Tests: `npm test`. Tipos: `npm run typecheck`.

Pantallas según los permisos del usuario: **Caja** (`cash.operate`), **Entradas** (`inventory.receive`) y **Existencias** (`inventory.view`).

## Documentación
- [Arquitectura](docs/arquitectura.md) · [Constitución](docs/constitution.md)
- [Spec 001 — MVP](specs/001-mvp/spec.md) y sus [tareas](specs/001-mvp/tasks.md)
- Reglas para agentes de IA: [AGENTS.md](AGENTS.md)
