# Tareas — Spec 005

> Spec aprobada por el equipo (PR #36, 2026-10-17). Decisiones en spec.md.

- [x] **T1** Catálogo fiscal: separar *exento* de *excluido* en la tarifa de IVA y catálogo de **clientes** (tipo y número de documento con dígito de verificación, nombre o razón social, correo, responsabilidades) con *consumidor final* creado por migración. API y admin.
  - `vat_excluded` en el producto (restricción: solo con tarifa 0 %) y copiado a la línea de venta; no hizo falta migrar datos, porque los productos actuales son todos del 19 %. App `customers` con el dígito de verificación de la DIAN (probado con 800197268-4 y 860034313-7) y permisos `cash.operate` o `sales.create`, sin permisos nuevos.
- [ ] **T2** **Numeración por caja:** resolución DIAN (número, fecha, prefijo, rango, vigencia) por caja; consecutivo sin huecos ni repetidos con bloqueo de base de datos (dos cajas a la vez, probado en PostgreSQL); avisos cuando quedan pocos números o se acerca el vencimiento.
- [ ] **T3** **Documento fiscal** por venta, anulación y devolución (DE-POS, FE, nota de ajuste, nota crédito) con estado, CUDE/CUFE, QR e historial; **adaptador** de proveedor con una sola interfaz y **proveedor simulado** para desarrollo y tests.
- [ ] **T4** **Cola de envío** en el servidor: comando programado con reintentos y espera creciente, estados `pendiente → enviado → validado/rechazado`, y bandeja del supervisor con rechazados y pendientes por vencer el plazo.
- [ ] **T5** **Contingencia:** ventas sin conexión con documento de contingencia numerado en la caja (bloque de números reservado por equipo para no chocar sin servidor), transmisión al volver y alerta si alguno se acerca a las 48 horas.
- [ ] **T6** **Caja:** consumidor final por defecto; buscar o crear cliente; marcar "pedir factura electrónica". **Tiquete de 80 mm** con los datos del art. 19 y QR (impresión desde el navegador) y envío por correo opcional.
- [ ] **T7** **Proveedor real** (cuando el equipo lo elija): adaptador, credenciales por variables de entorno y set de pruebas de habilitación de la DIAN en el ambiente de pruebas.
- [ ] **T8** Prueba de punta a punta: venta en línea, factura a pedido, anulación, devolución parcial y venta sin conexión transmitida al volver, todo validado en el ambiente de pruebas.
