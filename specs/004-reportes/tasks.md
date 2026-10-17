# Tareas — Spec 004

> Spec aprobada por el equipo (PR #29, 2026-10-16), incluida la regla de devoluciones. Decisiones en spec.md.

- [x] **T1** Costo promedio ponderado en entradas, ventas y devoluciones; permiso `reports.costs` (migración de datos); costo estimado para las ventas anteriores.
  - `inventory/costing.py` (fórmula y `replay_costs`). `StockLevel.average_cost` y costos con 4 decimales. La migración recalcula todo el kardex en orden; en la base de demostración marcó 17 salidas como costo estimado y los promedios coinciden con los costos de compra.
- [x] **T2** API de reportes de ventas y de productos (`/api/reports/sales/`, `/api/reports/products/`).
  - App `reports` (`period.py`, `services.py`). Netos de anulaciones y devoluciones; la devolución resta el día en que se hizo, en la caja del reembolso y al vendedor de la venta. "Sin movimiento" = sin ventas válidas en el período (una venta anulada no cuenta).
- [ ] **T3** API de inventario valorizado, márgenes y arqueos (`/api/reports/inventory/`, `/api/reports/margins/`, `/api/reports/shifts/`), con `reports.costs` para márgenes e inventario valorizado.
- [ ] **T4** Pantalla Reportes: hoy por defecto, accesos rápidos y rango; pestañas por reporte y tablas.
- [ ] **T5** Exportar cada reporte a CSV (`;` y coma decimal).
- [ ] **T6** Prueba de punta a punta: comparar los reportes con los datos de la base de demostración y con los arqueos.
