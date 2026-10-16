# AGENTS.md — Inventario-POS
Inventario y punto de venta para ferreterías: entradas a bodega, ventas que descuentan stock, caja y usuarios con roles. App web con modo sin conexión en las cajas.

## Stack y estructura
- Backend: Python 3.12+, Django + Django REST Framework, PostgreSQL en producción (SQLite en desarrollo y tests), en `backend/`.
- `backend/apps/accounts` usuarios, roles y permisos · `apps/catalog` productos y unidades · `apps/inventory` bodegas, kardex y existencias · `apps/sales` ventas · `apps/cash` cajas, turnos y pagos.
- Frontend: React + Vite + TypeScript en `frontend/`. `src/api.ts` cliente y tipos · `src/cart.ts` lógica del carrito y cobro (sin React) · `src/pages/` pantallas.
- `docs/` arquitectura, constitución y despliegue · `specs/NNN-nombre/` specs.
- Producción: `Dockerfile` multi-etapa (compila el frontend y lo sirve Django con WhiteNoise; gunicorn) + `docker-compose.yml` con PostgreSQL. Prueba de humo: `scripts/smoke-test.sh` (el CI la ejecuta).

## Comandos del backend (desde `backend/`)
- Entorno: `python -m venv .venv` y `.venv\Scripts\pip install -r requirements-dev.txt`.
- Tests: `.venv\Scripts\python -m pytest` (pytest-django; **no** `manage.py test`, que no ve los tests de pytest).
- Migraciones: `.venv\Scripts\python manage.py makemigrations` y `migrate`. Servidor: `manage.py runserver`.
- PostgreSQL: variables `DB_ENGINE=postgres`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`.

## Comandos del frontend (desde `frontend/`)
- `npm install`, `npm run dev` (puerto 5173, reenvía `/api` a Django en el 8000), `npm test` (Vitest), `npm run typecheck`, `npm run build`.

## Convenciones
- Código e identificadores en inglés; mensajes al usuario, docs y commits en español.
- La lógica de negocio va en `services.py`, no en vistas ni serializers.
- Permisos de la API con `require("codigo.permiso")` de `apps/accounts/drf.py`, nunca por nombre de rol.
- En el frontend, el dinero va en centavos enteros (`money.ts`), nunca en `float` de pesos. El backend recalcula y es la fuente de verdad.
- Cada intento de cobro o de entrada genera su `client_uuid` una sola vez: un reintento reutiliza el mismo.
- Sin conexión: la lógica va en `offline.ts` (sin React ni IndexedDB, para poder probarla) y el estado en `sync.tsx`. Solo se va a la cola si el servidor es inalcanzable (`isUnreachable`), nunca ante un 400 o un 500.
- El service worker solo se registra en el build de producción. Para probarlo: `npm run build` y `npx vite preview` (puerto 4173).

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
- En los pagos, `amount` es lo que se abona a la venta; las vueltas solo existen en efectivo. Efectivo esperado al cierre = base + pagos en efectivo de ventas no anuladas − reembolsos en efectivo.
- **El arqueo de un turno cerrado nunca cambia.** Por eso una venta solo se anula mientras su turno siga abierto; después se hace una devolución (`sales/returns.py`), que reembolsa desde el turno abierto actual.
- En devoluciones parciales, la última parte de una línea reembolsa el resto exacto del total, para no perder ni sobrar centavos.
- Autenticación por sesión en cookie + CSRF (`/api/auth/`), no JWT. Los usuarios no se borran, se desactivan. Siempre debe quedar al menos un usuario activo con `users.manage` (`accounts/services.py`).

## Forma de trabajar
- Lee `docs/constitution.md`, `MEMORY.md` y la spec activa antes de tocar código.
- Cambios medianos o grandes: spec en `specs/` y aprobación antes de tocar código. Pequeños: modo plan.
- Al terminar: resume cambios, resultado de los tests y decisiones que deba revisar.

## Límites
- ✅ Siempre: tests en verde antes de dar algo por hecho; actualizar `MEMORY.md`.
- ✅ El CI (`.github/workflows/tests.yml`) corre en cada PR: no fusionar con el CI en rojo.
- ⚠️ Pregunta antes: dependencias nuevas, cambios en el modelo de permisos o en el contrato de la API de sincronización.
- ⚠️ Toda variable de entorno nueva va en `.env.example` y en la tabla de `docs/despliegue.md`.
- 🚫 Nunca: guardar claves o tokens en el repo (`.env` está ignorado); borrar o editar movimientos de inventario existentes.
