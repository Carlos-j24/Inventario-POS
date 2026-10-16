# AGENTS.md — Inventario-POS
Inventario y punto de venta para ferreterías: entradas a bodega, ventas que descuentan stock, caja y usuarios con roles. App web con modo sin conexión en las cajas.

## Stack y estructura
- Backend: Python 3.12+, Django + Django REST Framework, PostgreSQL en producción (SQLite en desarrollo y tests), en `backend/`.
- `backend/apps/accounts` usuarios, roles y permisos · `apps/catalog` productos y unidades · `apps/inventory` bodegas, kardex y existencias.
- Frontend (pendiente): React + Vite como PWA, en `frontend/`.
- `docs/` arquitectura y constitución · `specs/NNN-nombre/` specs.

## Comandos (desde `backend/`)
- Entorno: `python -m venv .venv` y `.venv\Scripts\pip install -r requirements-dev.txt`.
- Tests: `.venv\Scripts\python -m pytest` (pytest-django; **no** `manage.py test`, que no ve los tests de pytest).
- Migraciones: `.venv\Scripts\python manage.py makemigrations` y `migrate`. Servidor: `manage.py runserver`.
- PostgreSQL: variables `DB_ENGINE=postgres`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`.

## Convenciones
- Código e identificadores en inglés; mensajes al usuario, docs y commits en español.
- La lógica de negocio va en `services.py`, no en vistas ni serializers.
- Permisos de la API con `require("codigo.permiso")` de `apps/accounts/drf.py`, nunca por nombre de rol.

## Reglas de dominio / trampas
- **El stock solo se mueve con `inventory.services.record_movement`.** Nunca escribir `StockLevel.quantity` a mano.
- Los movimientos (kardex) no se editan ni se borran: los errores se corrigen con un movimiento de ajuste.
- Cantidades en la **unidad base** del producto (metro, unidad, kilo). Las presentaciones (rollo, caja, bulto) se convierten con su factor.
- Todo lo que el POS crea sin conexión lleva un `client_uuid`: reenviarlo no debe duplicar nada.
- Una venta sin conexión puede dejar stock negativo; se acepta y se marca `needs_review` para que bodega lo revise.
- Los permisos son fijos en código (se añaden con una migración de datos); los roles son datos que edita el administrador.
- Dinero y cantidades siempre con `Decimal`, nunca `float`.

## Forma de trabajar
- Lee `docs/constitution.md`, `MEMORY.md` y la spec activa antes de tocar código.
- Cambios medianos o grandes: spec en `specs/` y aprobación antes de tocar código. Pequeños: modo plan.
- Al terminar: resume cambios, resultado de los tests y decisiones que deba revisar.

## Límites
- ✅ Siempre: tests en verde antes de dar algo por hecho; actualizar `MEMORY.md`.
- ⚠️ Pregunta antes: dependencias nuevas, cambios en el modelo de permisos o en el contrato de la API de sincronización.
- 🚫 Nunca: guardar claves o tokens en el repo; borrar o editar movimientos de inventario existentes.
