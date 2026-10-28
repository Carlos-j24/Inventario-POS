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

### Datos de demostración

Para mostrar la app: una ferretería con dos semanas de ventas, arqueos (uno con faltante), una anulación, una devolución, un pedido por cobrar, una venta sin conexión para revisión, una baja por aprobar, un conteo, un traslado, un producto pendiente de precio, los datos del negocio (ficticios) y cotizaciones en todos sus estados. Usuarios: `admin.demo` (también entra al admin de Django), `marta.jefe`, `pedro.bodega`, `laura.caja`, `maria.caja`, `andres.ventas` y `sofia.super`.

Con `--taller`, la misma historia en un taller de motos con repuestos: el módulo de taller activo, `diana.recepcion` (Recepción de taller), clientes con sus motos (una con dueño anterior, una sin placa) y lavados cobrados todos los días como servicios (spec 010).

```bash
.venv\Scripts\python manage.py seed_demo --fresh
.venv\Scripts\python manage.py seed_demo --fresh --taller   # un taller de motos con el módulo de taller (spec 009)
```

`--fresh` borra `db.sqlite3` y la crea de nuevo (cierra antes el `runserver`); sin él, llena una base recién migrada. Las contraseñas salen una sola vez en la consola (una al azar por usuario) o, con `--password <clave>`, la misma para todos. Solo corre con `DEBUG`: nunca en producción.

## Arrancar el frontend (PWA)

Con el backend corriendo en el puerto 8000:

```bash
cd frontend
npm install
npm run dev
```

Abre http://localhost:5173. Vite reenvía `/api` a Django, así que el navegador ve un solo dominio (necesario para la sesión en cookie). Tests: `npm test`. Tipos: `npm run typecheck`.

Pantallas según los permisos del usuario: **Caja** (`cash.operate`), **Entradas** (`inventory.receive`), **Existencias** (`inventory.view`), **Productos** (`catalog.edit`; el precio con `catalog.edit_prices`), **Conteos** (`inventory.count`), **Ajustes** (los pide bodega y los aprueba `inventory.adjust`) y **Traslados** (`inventory.transfer`), además de las de ventas, reportes, DIAN y administración.

## Producción

Docker con PostgreSQL y un solo contenedor que sirve la app y la API: ver [docs/despliegue.md](docs/despliegue.md).

```bash
cp .env.example .env
docker compose up -d --build
```

## Documentación
- [Arquitectura](docs/arquitectura.md) · [Constitución](docs/constitution.md) · [Despliegue](docs/despliegue.md)
- Specs: [001 — MVP](specs/001-mvp/spec.md) · [002 — Pedidos](specs/002-pedidos/spec.md) · [003 — Supervisor y administrador](specs/003-supervisor-admin/spec.md) · [004 — Reportes](specs/004-reportes/spec.md) · [009 — Clientes y motos (taller)](specs/009-clientes-y-motos/spec.md) · [010 — Servicios (lavados)](specs/010-servicios/spec.md) (cada una con su `tasks.md`)
- Reglas para agentes de IA: [AGENTS.md](AGENTS.md)
