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

## Pedidos (spec 002)
- El vendedor arma un `Order` con precio congelado por línea y recibe un código de 4 dígitos, único en el día de negocio (hora de Bogotá). El pedido **no mueve inventario**.
- La caja lo carga por código (`/api/orders/code/<código>/`) y lo cobra por `POST /api/sales/` con `order` (+ `order_lines` si cobra menos). Bloquea el pedido, crea la venta con `salesperson` = vendedor y `seller` = cajero, y lo marca PAGADO en la misma transacción.
- Solo con conexión. Los pendientes de días anteriores cuentan como vencidos (`effective_status`); `manage.py expire_orders` deja el estado guardado al día.

## Roles y permisos
- `Permission`: códigos fijos (`inventory.receive`, `sales.void`…), creados por migraciones.
- `Role`: conjunto editable de permisos. Por defecto: Administrador, Supervisor, Jefe de bodega, Auxiliar de bodega, Ventas, Caja.
- `User.roles`: un usuario puede tener varios roles y sus permisos se suman.

## Modo sin conexión (T9)
1. **La app abre sin red.** Un service worker propio (`frontend/public/sw.js`, sin Workbox) guarda el HTML, JS y CSS al instalarse. La navegación va primero a la red (para recibir versiones nuevas) y, si no hay, usa la copia. `/api`, `/admin` y `/static` nunca pasan por la caché.
2. **Datos con copia local.** Catálogo, cajas y usuario se guardan en IndexedDB (`frontend/src/idb.ts`, almacén `kv`) cada vez que llegan del servidor (`cache.ts`). Sin red se usa la última copia y la caja avisa de qué fecha son los precios.
3. **Cola de ventas.** Al cobrar se intenta enviar la venta. Si el servidor no responde (sin red, 502/503/504 o más de 10 s), la venta se guarda en el almacén `outbox` con el **mismo `client_uuid`**, `offline=true` y el precio cobrado en cada línea. Si el primer envío sí llegó, el servidor la reconoce al sincronizar y no la duplica.
4. **Sincronización** (`offline.ts`, `sync.tsx`): al abrir la app, al volver la red, cada 30 s y con "Enviar ahora". Va en orden de creación y solo con las ventas **del usuario con sesión**, para que cada venta quede a nombre de quien la hizo. Se detiene sin red o con la sesión vencida (403). Una venta rechazada (400) queda marcada como "rechazada" y no se reintenta sola.
5. **En el servidor**, una venta sin conexión acepta stock negativo, respeta el precio cobrado y se acepta aunque su turno ya haya cerrado. En esos casos queda `needs_review` y aparece en la **bandeja de revisión** (`/api/sales/review/`, pantalla "Revisión", permiso `reports.view`). Quien la atiende la marca revisada con una nota; la marca `needs_review` se conserva para la historia.
6. **Sin conexión no se puede** abrir ni cerrar turno, anular, devolver ni registrar entradas: necesitan el servidor. Cerrar turno también exige que no haya ventas por enviar, para que el arqueo esté completo.
7. **Sesión:** la app guarda el usuario en IndexedDB y, sin red, abre con esa copia. Al salir se borra.

**Pendiente:** numeración legal por caja (prefijo y consecutivo local) cuando llegue la facturación electrónica. Hoy el número `V-000123` lo asigna el servidor al sincronizar.

## Autenticación
- Sesión de Django en cookie `HttpOnly` (12 h, configurable con `SESSION_COOKIE_AGE`) + token CSRF. Se eligió frente a JWT porque no añade dependencias y JavaScript no puede leer la cookie (menos riesgo ante XSS).
- Flujo de la PWA: `GET /api/auth/csrf/` → `POST /api/auth/login/` (con cabecera `X-CSRFToken`) → `GET /api/auth/me/` con roles y permisos para mostrar u ocultar opciones. El login admite 5 intentos por minuto (`LOGIN_RATE`).
- La PWA y la API se sirven desde el **mismo dominio**. Sin conexión no hay llamadas; al volver, si la sesión venció, el cajero inicia sesión de nuevo y la cola se reenvía sin duplicados.

## Pendiente de decidir
- Facturación electrónica DIAN: a través de un proveedor tecnológico autorizado. Una venta sin conexión se emite al sincronizar (o con contingencia).
