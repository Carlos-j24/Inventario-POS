# Tareas — Spec 013

> Aprobada (2026-11-03, PR #99). Decisiones en spec.md.

- [x] **T1** Backend: casilla `Business.simple_mode` (migración, admin) que llega a la sesión del usuario; `Product.income_line` (Repuestos, Taller, Lavadero) con sus reglas, y la línea de venta y la de devolución copian la línea de ingreso. (Reglas 1 y 6)
  - `Business.simple_mode` llega a la sesión (`/api/auth/me/`). `Product.income_line` se ajusta solo en `save()` y `clean()` (un producto con inventario siempre es Repuestos; un servicio sin línea, Taller) y una restricción de la base de datos lo exige; se ve y se edita en la API de productos, la de la caja y el admin. La línea de venta lo copia al vender. Cambio frente a la tarea: la línea de devolución **no** lleva su propia copia, porque la toma de su línea vendida, que nunca cambia (sería un dato repetido). Las migraciones ponen los servicios existentes en Taller, o en Lavadero si la categoría dice "lavad", y lo copian a sus líneas vendidas. 9 tests y 13 fallos a propósito; uno sobrevivía (el test de la migración partía con el lavado ya en Lavadero) y se corrigió el test. Ese test también mostró que la migración dependía de que todo empezara en Repuestos; ahora decide solo por la categoría.
- [ ] **T2** Frontend: menú de la versión sencilla (pantallas ocultas, Usuarios sin la pantalla Roles) y "Línea de ingreso" en Productos para los servicios. (Reglas 2, 3 y 6)
- [ ] **T3** Orden simplificada: con la casilla, las líneas quedan aprobadas al agregarlas, la orden no pasa por "Esperando aprobación" y el mecánico es opcional, en la API y en la pantalla Órdenes. (Regla 4)
- [ ] **T4** Factura en hoja carta: impresión de la venta desde la caja y desde Ventas, reutilizando la maqueta de las cotizaciones; se comprueba imprimiendo a PDF. (Regla 5; decisión 6)
- [ ] **T5** Gastos: modelo, categorías editables, API y pantalla, con corrección y anulación con rastro y la salida de efectivo del turno si se paga de la caja. (Regla 7; decisiones 7 y 8)
- [ ] **T6** Resumen en Reportes: ingresos por línea, costo, ganancia bruta, gastos y ganancia neta por día, semana o mes, con CSV. (Regla 8)
- [ ] **T7** Demo (`seed_demo --taller` con la versión sencilla y gastos), prueba en el navegador de las dos demos y cierre: `docs/arquitectura.md`, `MEMORY.md` y la spec. (Reglas 9 y 10)
