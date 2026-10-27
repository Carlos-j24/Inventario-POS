# Tareas — Spec 010

> Spec en borrador (2026-10-27): se empieza al aprobar el PR. Decisiones en spec.md.

- [ ] **T1** Backend, modelo: `Product.is_service` (migración); un servicio sin presentaciones, sin fracciones y sin stock mínimo; no se cambia de producto a servicio (ni al revés) si ya tiene movimientos o ventas. `SaleLine.movement` y el de las líneas de devolución pasan a opcionales, con una restricción de la base de datos que solo deja la línea sin movimiento si es de un servicio. Admin y API de productos con la casilla. (Reglas 1, 2, 3 y 10)
- [ ] **T2** Venta, anulación, devolución, pedidos y cotizaciones con servicios: sin movimiento ni revisión por stock, en línea y sin conexión; el aviso de stock de los pedidos no aplica a los servicios. (Reglas 4 a 6)
- [ ] **T3** Inventario y reportes: servicios fuera de Entradas, Ajustes, Conteos, Traslados, Existencias, inventario valorizado y alertas, y rechazados por la API de inventario. En ventas y más vendidos con su cantidad (sacada de la línea, ya que no tienen movimiento); en márgenes marcados como servicio, sin costo y aparte de la mercancía. (Reglas 7 y 8)
- [ ] **T4** Frontend: casilla "Es un servicio" en Productos (sin stock mínimo ni presentaciones), la Caja no muestra existencias de los servicios, y Existencias y las pantallas de inventario no los ofrecen. Márgenes con los servicios aparte. (Reglas 1, 4, 7 y 8)
- [ ] **T5** `seed_demo --taller`: categoría "Lavadero" con dos o tres lavados y ventas con lavados en la historia (alguna con lavado y repuesto, una sin conexión). (Regla 11)
- [ ] **T6** Prueba en el navegador con la demo de taller (cobrar, anular y devolver lavados, en línea y sin conexión; reportes) y con la de ferretería, y cierre: `docs/arquitectura.md`, `MEMORY.md` y la spec.
