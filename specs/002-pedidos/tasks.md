# Tareas — Spec 002

> Spec aprobada por el equipo (PR #13, 2026-10-16). Decisiones en spec.md.

- [x] **T1** Modelo `Order` + `OrderLine` (estado, código diario, vendedor, vencimiento) y `Sale.salesperson`. Migraciones. (Historias 1 y 5)
  - El código es único por día y de 4 dígitos (restricciones en la base de datos). Un pedido pagado tiene su venta y viceversa. La fecha de negocio es la de Bogotá. Las ventas anteriores quedan con el cajero como vendedor.
- [x] **T2** Servicios: crear, cancelar y vencer pedidos, y generar el código sin choques entre pedidos del mismo día. (Historias 1 y 2)
  - `apps/sales/orders.py`. Código aleatorio (no se adivina el siguiente) con reintento si choca. Avisos de stock sin bloquear. Comando diario `manage.py expire_orders`.
- [ ] **T3** Cobro de pedido: `create_sale` acepta un pedido; las líneas cobradas son un subconjunto del pedido; se cobra una sola vez, con bloqueo. (Historia 3)
- [ ] **T4** API: crear, listar, cancelar, buscar por código y cobrar. Permisos `sales.create`, `cash.operate` y `sales.void`. (Historias 1 a 4)
- [ ] **T5** Pantalla "Pedidos" del vendedor: buscar, carrito, crear, código grande, mis pendientes y cancelar. (Historias 1 y 2)
- [ ] **T6** En Caja: campo "Código de pedido", lista de pendientes, carga del pedido en el carrito y cobro. (Historias 3 y 4)
- [ ] **T7** Mostrar vendedor y cajero en la venta (admin y API). Prueba de punta a punta en el navegador con dos usuarios. (Historia 5)
