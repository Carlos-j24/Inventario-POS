# Tareas — Spec 003

> Spec aprobada por el equipo (PR #21, 2026-10-16). Decisiones en spec.md.

- [x] **T1** Backend: `GET /api/sales/` (buscar y filtrar), el detalle de la venta con sus devoluciones y lo ya devuelto por línea, y los permisos del detalle. (Historias 1 y 4)
  - `GET /api/sales/`: hoy por defecto; `?number=` (V-000123, v123 o 123, en cualquier fecha), `?date=`, `?register=`, `?status=`, `?needs_review=1`; máximo 200. El detalle trae `returns`, `returned_quantity` por línea, `register` y `shift_open`.
- [x] **T2** Backend: `POST /api/auth/password/`, marca `must_change_password` al crear o resetear un usuario, y bloqueo de la API mientras esté marcada. (Historias 5 y 7)
  - El bloqueo vive en `require()`/`require_any()` y en el permiso por defecto (`IsAuthenticatedAndReady`); solo `me`, `password` y `logout` lo permiten (`AllowWhilePasswordChange`). Cambiar la contraseña mantiene la sesión y comparte el límite de intentos del login.
- [x] **T3** Pantalla Ventas: buscar, listar y ver el detalle. (Historia 1)
  - Visible con `sales.void` o `reports.view` (la navegación ahora acepta varios permisos por pantalla). Probado en Chrome como sofia.super: lista de hoy, búsqueda "v4" de una venta de ayer y detalle con vendedor, cajero, pedido, IVA, pagos y devoluciones.
- [ ] **T4** Anular y devolver desde el detalle (con elección de la caja abierta para el reembolso). Enlace desde la bandeja de revisión. (Historias 2, 3 y 4)
- [ ] **T5** Pantalla Usuarios: lista, alta, roles, activar/desactivar y contraseña nueva. (Historia 5)
- [ ] **T6** Roles y permisos en lenguaje claro (todos editables). "Cambiar mi contraseña" para todos y pantalla de cambio obligatorio. (Historias 6 y 7)
- [ ] **T7** Prueba de punta a punta en el navegador: alta de un cajero nuevo que vende, y una devolución hecha por el supervisor que se refleja en el arqueo.
