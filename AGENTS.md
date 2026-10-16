# AGENTS.md — Inventario-POS
Inventario y punto de venta para ferreterías: entradas a bodega, ventas que descuentan stock, caja y usuarios con roles. App web con modo sin conexión en las cajas.

## Stack y estructura
- Backend: Python 3.12+, Django + Django REST Framework, PostgreSQL en producción (SQLite en desarrollo y tests), en `backend/`.
- `backend/apps/accounts` usuarios, roles y permisos · `apps/catalog` productos y unidades · `apps/inventory` bodegas, kardex y existencias · `apps/sales` ventas · `apps/cash` cajas, turnos y pagos.
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
- Los precios de venta **incluyen IVA** (precio al público). El IVA se separa por línea y se redondea al centavo.
- Venta en línea: precio del catálogo y sin stock negativo. Venta sin conexión: se respeta el precio cobrado y se acepta negativo, marcando `needs_review`.
- Toda venta pertenece al turno abierto de una caja y sale de la bodega de esa caja. Una venta sin conexión que llega con el turno ya cerrado se acepta y se marca `needs_review`.
- En los pagos, `amount` es lo que se abona a la venta; las vueltas solo existen en efectivo. Efectivo esperado al cierre = base + pagos en efectivo de ventas no anuladas.

## Forma de trabajar
- Lee `docs/constitution.md`, `MEMORY.md` y la spec activa antes de tocar código.
- Cambios medianos o grandes: spec en `specs/` y aprobación antes de tocar código. Pequeños: modo plan.
- Al terminar: resume cambios, resultado de los tests y decisiones que deba revisar.

## Límites
- ✅ Siempre: tests en verde antes de dar algo por hecho; actualizar `MEMORY.md`.
- ✅ El CI (`.github/workflows/tests.yml`) corre en cada PR: no fusionar con el CI en rojo.
- ⚠️ Pregunta antes: dependencias nuevas, cambios en el modelo de permisos o en el contrato de la API de sincronización.
- 🚫 Nunca: guardar claves o tokens en el repo; borrar o editar movimientos de inventario existentes.
