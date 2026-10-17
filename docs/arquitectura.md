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

## Supervisor y administración (spec 003)
- **Ventas** (`sales.void` o `reports.view`): `GET /api/sales/` lista las de hoy o busca por número; el detalle trae devoluciones y si su turno sigue abierto. Anular exige el turno abierto; si no, se devuelve y el reembolso sale de una caja con turno abierto, sin tocar arqueos cerrados.
- **Usuarios y Roles** (`users.manage`): la contraseña que pone el administrador es temporal (`must_change_password`). Hasta cambiarla, la API solo permite `me`, `password` y `logout`; el bloqueo vive en `require()`, `require_any()` y el permiso por defecto.

## Reportes (spec 004)
- **Costo promedio ponderado**: cada entrada recalcula `StockLevel.average_cost`; cada salida guarda el promedio del momento en `unit_cost`, y una devolución vuelve con el costo con que salió (`inventory/costing.py`).
- **API** (`reports.view`, solo lectura): `GET /api/reports/sales/` (totales, por día, caja, vendedor y medio de pago) y `GET /api/reports/products/` (más vendidos por cantidad y por valor, y sin movimiento). Período `?from=AAAA-MM-DD&to=…` en hora de Bogotá, hoy por defecto y máximo un año; filtros `register`, `salesperson` y `limit`.
- **Con costos** (`reports.costs`, solo Administrador por defecto): `GET /api/reports/inventory/` (foto actual: existencias × costo promedio, por producto y total; marca bajo mínimo y negativos; una existencia negativa vale 0; `?warehouse`) y `GET /api/reports/margins/` (venta neta sin IVA − costo guardado en cada salida, con % y aviso de costo estimado).
- **Arqueos** (`reports.view`): `GET /api/reports/shifts/` lista los turnos cerrados en el período (por fecha de cierre) con lo que entró por cada medio, esperado, contado y diferencia; totaliza faltantes y sobrantes.
- Las ventas anuladas no cuentan. Una devolución resta el día en que se hizo, en la caja de donde salió el reembolso y al vendedor de la venta: así el reporte cuadra con los arqueos.
- El dinero sale como texto con 2 decimales y las cantidades con 3, nunca como número de coma flotante.
- **Pantalla Reportes** (`pages/Reports.tsx`): hoy por defecto, accesos rápidos (ayer, esta semana desde el lunes, este mes) y rango libre; filtro de caja. Pestañas Ventas, Productos y Arqueos; Inventario valorizado y Márgenes solo con `reports.costs`. Solo muestra lo que calcula el servidor; "Descargar CSV" arma el archivo en el navegador con esa misma respuesta (`;`, coma decimal, BOM UTF-8).

## Facturación electrónica (spec 005)
- **Exento y excluido:** `Product.vat_excluded` (no causa IVA) solo con tarifa 0 %, garantizado por una restricción de la base; se copia a `SaleLine` al vender para que el documento fiscal sepa qué era en ese momento.
- **Clientes** (`apps.customers`): tipo de documento con los códigos de la DIAN, dígito de verificación del NIT calculado (módulo 11, `rules.py`), persona natural o jurídica, correo y responsabilidades fiscales. El **consumidor final** (`222222222222`) lo crea una migración y no se puede modificar. API `GET/POST /api/customers/` (búsqueda `?q=` por número o nombre, máximo 20), `GET/PATCH /api/customers/<id>/` y `GET /api/customers/final-consumer/`, con `cash.operate` o `sales.create`. Los clientes no se borran: se desactivan.
- **Numeración** (`apps.invoicing`): `NumberingResolution` por caja y tipo de documento (POS, factura, contingencia), con número y fecha de la resolución, vigencia (máximo 2 años, validado), prefijo de hasta 4 caracteres y rango; los rangos de un mismo prefijo no se cruzan. `take_number()` bloquea con `select_for_update` todas las resoluciones vigentes de la caja dentro de la transacción del documento: si este se deshace, el número no se gasta (sin huecos ni repetidos). Si hay varias vigentes usa primero la más antigua; si no hay, explica por qué (sin resolución, agotada, aún no rige o vencida). Avisos cuando quedan pocos números (el mayor entre 100 y el 10 % del rango) o faltan 30 días o menos. Se cargan en el admin (rango y prefijo fijos una vez creada); `GET /api/invoicing/numbering/` con `cash.operate` o `reports.view`.

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
