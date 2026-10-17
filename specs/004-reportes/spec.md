# Spec 004 — Reportes

> Estado: ✅ **completada (2026-10-17)**. Tareas en tasks.md (T1–T6, PRs #30–#35).

## Problema
El dueño de la ferretería no tiene cómo saber, sin hacer cuentas a mano, cuánto vendió, qué se vende más, cuánto vale lo que tiene en bodega ni cuánto gana. Los datos existen (ventas, pagos, devoluciones, kardex, arqueos), pero no hay reportes.

Además, **hoy solo las entradas guardan costo**: cuando se vende, no queda registrado cuánto costó lo vendido. Sin eso no se puede calcular el margen ni valorizar bien el inventario.

## Objetivo
Una pantalla **Reportes** (permiso `reports.view`; costos con `reports.costs`) con cinco reportes por período y descarga en CSV, y el registro del **costo de lo vendido** en cada venta.

## Reportes
1. **Ventas del período:** total, subtotal e IVA; número de ventas y ticket promedio; por día, por caja, por vendedor y por medio de pago. Neto de anulaciones y devoluciones.
2. **Productos:** los más vendidos por cantidad y por valor, y los que **no se movieron** en el período.
3. **Inventario valorizado** (`reports.costs`): existencias × costo promedio, por producto y total; marca los que están bajo el mínimo o en negativo.
4. **Márgenes** (`reports.costs`): venta neta (sin IVA) − costo de lo vendido, por producto y total, con el margen en %.
5. **Arqueos:** turnos cerrados del período con caja, quién abrió y cerró, esperado, contado y diferencia; total de faltantes y sobrantes.

## Reglas
- Las fechas son **fechas de negocio** en hora de Bogotá. Una venta cuenta el día en que ocurrió (`occurred_at`), aunque haya llegado después sin conexión.
- Una **anulación** saca la venta del período (como si no hubiera existido).
- Una **devolución** resta en el día **en que se hizo**, no en el de la venta, porque ese día salió el dinero. *(Regla propuesta; el equipo puede cambiarla.)*
- El **costo de lo vendido** se fija en el momento de la venta y no cambia después, aunque cambie el costo del producto.
- Los reportes se calculan en el servidor; la pantalla solo los muestra.

## Lo que cambia en el backend
- Cada movimiento de salida (venta) guarda su **costo unitario** según el método de costo (decisión 1). Las devoluciones devuelven al inventario con ese mismo costo.
- Endpoints de solo lectura en `/api/reports/…` con `?from=` y `?to=` (y `?register=`, `?salesperson=` donde aplique).
- Las ventas anteriores a esta spec no tienen costo guardado: se les asigna el costo vigente en una migración y se marcan como **costo estimado**.

## Decisiones (equipo, 2026-10-16)
1. **Costo promedio ponderado.** Cada entrada recalcula el costo promedio por producto y bodega: `(existencias × costo actual + cantidad × costo de la entrada) ÷ (existencias + cantidad)`. Las ventas salen al costo promedio de ese momento y las devoluciones vuelven al costo con que salieron. Si las existencias estaban en negativo o en cero, el nuevo promedio es el costo de la entrada.
2. **Período: hoy por defecto**, con accesos rápidos (ayer, esta semana, este mes) y rango libre de fechas. Sin comparación con el período anterior por ahora.
3. **Exportar a CSV** cada reporte (separador `;` y coma decimal, para que Excel en español lo abra bien).
4. **Permiso nuevo `reports.costs`**, solo para el rol Administrador por defecto, creado con una migración de datos. Protege **márgenes** e **inventario valorizado** (muestran costos). Con `reports.view` se ven ventas, productos y arqueos.

## Fuera de esta spec
Gráficas avanzadas, reportes programados por correo, contabilidad (cuentas, balances), facturación electrónica DIAN y comisiones de vendedores.

## Criterios de aceptación
- La suma del reporte de ventas por día coincide con la suma de las ventas no anuladas menos las devoluciones del período.
- El total por medio de pago de un día coincide con los arqueos de los turnos de ese día (esperado − base).
- El costo de una venta no cambia si después entra mercancía a otro costo.
- El inventario valorizado coincide con las existencias × costo vigente.
- Un usuario sin `reports.view` no ve la pantalla, y la API le responde 403.
- Con `reports.view` pero sin `reports.costs`, no se ven márgenes ni inventario valorizado (ni en pantalla ni por la API).
- Con costo promedio: entrar 10 a $1.000 y luego 10 a $2.000 deja el costo en $1.500; vender 5 registra $7.500 de costo.
- El CSV descargado tiene las mismas cifras que la pantalla.
