# Tareas — Spec 001

- [x] **T1** Usuarios, roles y permisos con roles por defecto y permiso DRF `require()`. (Historia 1)
- [x] **T2** Catálogo: categorías, unidades, productos, presentaciones con factor, IVA. (Historia 2)
- [x] **T3** Inventario: bodegas, kardex, existencias, `record_movement` idempotente; API de entradas, existencias y kardex. (Historias 3 y 8)
- [x] **T4** Ventas: venta + líneas (precio, IVA por línea) + descuento de stock en una transacción; API idempotente con `client_uuid`. (Historia 4)
  - Descuentos por línea quedan para la T5 o una tarea propia (requieren permiso y tope por rol).
- [ ] **T5** Caja: turnos, base, pagos por medio, arqueo y cierre. (Historia 6)
- [ ] **T6** Anulación y devolución con permiso `sales.void`. (Historia 7)
- [ ] **T7** Autenticación para la PWA y API de usuarios y roles para el administrador. (Historia 1)
- [ ] **T8** Frontend PWA: inicio de sesión, POS, entradas a bodega, existencias. (Historias 3, 4 y 8)
- [ ] **T9** Modo sin conexión: catálogo en IndexedDB, cola de ventas, sincronización y bandeja `needs_review`. (Historia 5)
- [ ] **T10** CI con GitHub Actions (pytest) y despliegue con Docker + PostgreSQL.
