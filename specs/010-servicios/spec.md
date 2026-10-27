# Spec 010 — Servicios: lavados (módulo de taller, etapa 2)

> Estado: **aprobada (2026-10-27)** en el PR #74. Decisiones tomadas con Carlos el 2026-10-27. Tareas en tasks.md.

## Problema
Arias cobra lavados en la caja (alcance confirmado el 2026-10-27, cotizado aparte). Hoy la caja solo vende **productos con inventario**: cada línea vendida exige un movimiento de kardex (`SaleLine.movement`), en línea no se vende sin stock y una venta que deja stock negativo queda para revisión. Un lavado no tiene existencias: si se creara como producto, nunca habría stock para venderlo en línea y, sin conexión, cada lavado dejaría el inventario en negativo y la venta para revisión. Además ensuciaría Existencias, Conteos y el inventario valorizado.

Lo mismo pasará con la **mano de obra** de las órdenes de trabajo (spec 011).

## Objetivo
Que la caja cobre un lavado como cobra un repuesto (buscarlo, agregarlo, cobrar, anular, devolver, facturar), sin que toque el inventario.

## Reglas
1. **Servicio**: una casilla "Es un servicio" en el producto. Un servicio se busca, se cobra y se factura como cualquier producto, con su precio, su IVA, su categoría y su código de barras si lo tiene, pero **no mueve inventario**: no tiene existencias, ni stock mínimo, ni costo, ni presentaciones (se vende por unidad entera).
2. Un producto que ya tiene movimientos de inventario no puede pasar a servicio, ni un servicio con ventas volver a producto: se crea otro. Así el kardex y los reportes nunca mezclan las dos cosas.
3. **Precio fijo**, un servicio por tipo de lavado (por ejemplo "Lavado moto hasta 150 cc", "Lavado moto alto cilindraje"), con su historial de precios como cualquier producto. Si la caja cobra otro precio, la venta queda para revisión como hoy.
4. **Caja**: el servicio se vende en línea y sin conexión sin mirar existencias y sin dejar la venta para revisión por stock. En la pantalla no muestra existencias.
5. **Anular y devolver** una venta con servicios devuelve el dinero de esas líneas sin movimientos de inventario. Los productos de la misma venta vuelven a la bodega como hoy.
6. **Pedidos y cotizaciones** aceptan servicios; el aviso de "no alcanza el stock" no aplica a ellos.
7. **Inventario**: los servicios no salen en Entradas, Ajustes, Conteos, Traslados ni Existencias, ni en el inventario valorizado ni en las alertas de stock bajo. La API de inventario los rechaza.
8. **Reportes**: los servicios salen en ventas y productos más vendidos con su cantidad y su total. En márgenes salen marcados como servicio y sin costo (su margen es todo lo cobrado), y el total de márgenes los separa de los productos para no inflar el margen de la mercancía.
9. **DIAN**: un servicio va en el documento electrónico como una línea más; lo que el proveedor real pida distinto para servicios (unidad de medida) se resuelve en la spec 005, T7.
10. Crear o cambiar un servicio pide los mismos permisos que un producto (`catalog.edit`, y el precio con `catalog.edit_prices`). Los servicios **no dependen del módulo de taller**: cualquier negocio los puede usar.
11. `seed_demo --taller` siembra los lavados y algunas ventas con lavados en su historia. La demo de la ferretería queda igual.
12. Sin librerías nuevas ni permisos nuevos.

## Decisiones (2026-10-27)
1. **El servicio es un producto con la casilla "Es un servicio"**: reutiliza la caja, los pedidos, las cotizaciones, las devoluciones, los reportes y la DIAN, y la mano de obra de la spec 011 usará lo mismo. _Descartado:_ un catálogo de servicios aparte (habría que repetir todo eso para él).
2. **Precio fijo, un servicio por tipo de lavado.** Cambiar el precio en la caja deja la venta para revisión, como con un repuesto. _Descartado:_ un precio sugerido que la caja cambia libremente en cada lavado.
3. **El cobro del lavado no anota la moto por ahora.** La moto queda ligada a los trabajos con las órdenes de trabajo (011) y el historial (012). _Descartado por ahora:_ la placa opcional en la venta.
4. **Sin lavadores ni comisiones por ahora**: se decide cuando Arias cuente cómo les paga. _Descartado por ahora:_ elegir el lavador en cada lavado y un reporte de lo que le corresponde.

## Fuera de alcance
- Placa de la moto en el cobro del lavado, turnos o cola de lavado (en espera, lavando, listo) y lavadores con comisión: decisiones 3 y 4.
- Mano de obra en órdenes de trabajo (spec 011), historial y recordatorios (spec 012).
- Paquetes o combos (lavado más cambio de aceite) y promociones (el quinto lavado gratis).

## Criterios de aceptación
- Con "Lavado moto hasta 150 cc" como servicio a $12.000, la caja lo cobra en línea sin que haya existencias, y la venta no queda para revisión.
- Una venta con un lavado y un aceite descuenta solo el aceite del inventario; al anularla, vuelve solo el aceite y se devuelven los $12.000 del lavado.
- Sin conexión, un lavado se cobra y al sincronizar no queda para revisión por stock.
- El lavado no aparece en Existencias, Entradas, Conteos, Ajustes, Traslados ni en el inventario valorizado, y la API de inventario lo rechaza.
- En el reporte de márgenes, el lavado sale marcado como servicio, sin costo, aparte de la mercancía.
- Un producto con movimientos no se puede marcar como servicio.
- `seed_demo --taller` deja lavados en el catálogo y en las ventas de la demo.
