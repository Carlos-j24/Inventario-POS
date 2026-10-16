# Spec 001 — MVP ferretería

## Objetivo
Una ferretería de un local puede registrar la mercancía que entra a bodega, vender desde una o varias cajas (aunque se caiga internet), cobrar y cerrar caja, y saber en todo momento cuánto tiene de cada producto.

## Usuarios y roles
| Rol | Puede |
|---|---|
| Administrador | Todo, incluido crear usuarios y roles |
| Supervisor | Vender, cobrar, anular y devolver, ver reportes |
| Jefe de bodega | Productos (sin precios), entradas, ajustes, conteos, reportes |
| Auxiliar de bodega | Entradas y conteos |
| Ventas | Crear ventas y cotizaciones, consultar existencias |
| Caja | Crear ventas, cobrar, abrir y cerrar caja |

## Historias
1. **Como administrador** creo usuarios, les asigno uno o varios roles y puedo crear roles nuevos eligiendo permisos.
2. **Como jefe de bodega** creo productos con su unidad base y presentaciones (rollo de 100 m, caja de 50 und).
3. **Como auxiliar de bodega** registro una entrada por presentación y el sistema la guarda en la unidad base con su costo.
4. **Como cajero** vendo con lector de código de barras o búsqueda, en cantidades fraccionadas si el producto lo permite, y la venta descuenta stock.
5. **Como cajero** sigo vendiendo sin internet; al volver la red, las ventas se sincronizan sin duplicarse.
6. **Como cajero** abro caja con una base, cobro en efectivo, tarjeta o transferencia y cierro con arqueo.
7. **Como supervisor** anulo una venta y su mercancía vuelve al inventario con un movimiento de devolución.
8. **Como jefe de bodega** veo el kardex de un producto, las existencias bajo el mínimo y los movimientos marcados para revisión.

## Criterios de aceptación
- El stock de cualquier producto es igual a la suma de sus movimientos.
- Sin el permiso correspondiente, la API responde 403 y no cambia nada.
- Reenviar el mismo documento (mismo `client_uuid`) no duplica stock ni ventas.
- Una venta en línea sin stock suficiente se rechaza; una sincronizada sin conexión se acepta y se marca para revisión.
- Un producto que no se vende fraccionado rechaza cantidades no enteras.

## Fuera del MVP
Compras y proveedores, varias bodegas y traslados, lotes y vencimientos, promociones, facturación electrónica DIAN, reportes avanzados.
