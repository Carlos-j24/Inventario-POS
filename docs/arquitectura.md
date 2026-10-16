# Arquitectura

```
┌──────────────── Navegador (PWA React) ────────────────┐
│ POS · Bodega · Admin                                  │
│ IndexedDB: catálogo, precios, ventas pendientes       │
│ Service Worker: la app abre sin internet              │
└──────────────┬──────────────────────────▲─────────────┘
               │ cola de sincronización   │ catálogo y stock
               │ (POST idempotente)       │ (GET con "desde")
┌──────────────▼──────────────────────────┴─────────────┐
│ Django + DRF                                          │
│ accounts · catalog · inventory · sales · cash         │
│ services.py: reglas de negocio en transacciones       │
└──────────────┬────────────────────────────────────────┘
               ▼
          PostgreSQL
```

## Inventario
- `StockMovement` es el kardex: cada línea guarda el tipo, la cantidad con signo en unidad base, el costo, el saldo resultante, el usuario y la fecha real (`occurred_at`) además de la fecha de registro.
- `StockLevel` es el saldo por producto y bodega. Solo lo toca `record_movement`, que bloquea la fila mientras escribe.
- Unidades: cada producto tiene una unidad base y presentaciones con factor (1 rollo = 100 m). Se compra en rollos y se vende en metros.

## Roles y permisos
- `Permission`: códigos fijos (`inventory.receive`, `sales.void`…), creados por migraciones.
- `Role`: conjunto editable de permisos. Por defecto: Administrador, Supervisor, Jefe de bodega, Auxiliar de bodega, Ventas, Caja.
- `User.roles`: un usuario puede tener varios roles y sus permisos se suman.

## Modo sin conexión
1. Al abrir el turno, el POS descarga el catálogo, los precios y el stock aproximado a IndexedDB.
2. Cada venta se crea en el navegador con un UUID y se guarda en una cola local.
3. Un proceso en segundo plano envía la cola cuando hay red. El servidor aplica cada documento una sola vez (`client_uuid` único): reenviar es seguro.
4. Las ventas sincronizadas usan `allow_negative=True`. Si el stock queda negativo, el movimiento se marca `needs_review` y aparece en la bandeja del jefe de bodega.
5. Sin conexión **no** se permiten anulaciones, ajustes ni cambios de precio: necesitan el servidor.
6. Numeración: cada caja tiene su propio prefijo y consecutivo local, para no chocar con las demás.

## Pendiente de decidir
- Autenticación de la PWA (sesión con cookie o JWT con renovación) y cuánto tiempo puede trabajar una caja sin volver a iniciar sesión.
- Facturación electrónica DIAN: a través de un proveedor tecnológico autorizado. Una venta sin conexión se emite al sincronizar (o con contingencia).
