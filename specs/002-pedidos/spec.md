# Spec 002 — Pedidos: el vendedor arma, la caja cobra

> Estado: **decisiones cerradas por el equipo (2026-10-16)**; pendiente aprobar el PR para empezar a programar.

## Problema
En una ferretería el vendedor atiende en el mostrador: asesora, busca el producto, mide el cable y corta el tubo. Quien cobra es la caja. Hoy el rol **Ventas** no puede registrar nada que termine en venta, porque vender exige cobrar (`cash.operate`, decidido en la T5). El vendedor no tiene cómo pasarle a la caja lo que el cliente se lleva, y su trabajo no queda registrado.

## Objetivo
El vendedor arma un **pedido** en su equipo. El cliente va a la caja con un **código**, y el cajero lo carga, lo cobra y lo convierte en venta. La venta registra **quién vendió** (vendedor) y **quién cobró** (cajero).

## Flujo
```
Vendedor (Ventas)                Cliente               Cajero (Caja)
arma el pedido ──▶ código 4821 ──▶ va a caja ──▶ teclea 4821 ──▶ revisa ──▶ cobra ──▶ venta V-000123
   │                                                                │
   └── puede cancelarlo mientras esté pendiente                     └── puede quitar lo que el cliente no lleve
```

## Historias
1. **Como vendedor** busco productos (por nombre, SKU o lector), elijo unidad y cantidad (12,5 m, 1 rollo) y creo el pedido. Veo un **código corto** grande para dictarlo o imprimirlo.
2. **Como vendedor** veo mis pedidos pendientes de hoy y puedo **cancelar** uno.
3. **Como cajero** tecleo o escaneo el código y el pedido aparece en el carrito con sus líneas. Puedo quitar líneas o bajar cantidades si el cliente se arrepiente, y cobro como siempre (pago mixto, vueltas).
4. **Como cajero** veo la lista de pedidos pendientes, por si el cliente no recuerda el código.
5. **Como administrador o supervisor** veo en cada venta quién la vendió y quién la cobró.

## Reglas
- El pedido **no mueve inventario**: el stock baja al cobrar, como cualquier venta. Dos pedidos pueden incluir el mismo producto.
- Un pedido se cobra **una sola vez**. Al cobrarlo queda `PAGADO` y ligado a su venta; cobrarlo de nuevo falla.
- Estados: `PENDIENTE` → `PAGADO` | `CANCELADO` | `VENCIDO`.
- Crear y cobrar pedidos **exige conexión**: el pedido se arma en un equipo y se cobra en otro. Sin red, la caja sigue vendiendo directo, como hoy.
- Permisos: crear y cancelar pedidos propios exige `sales.create` (Ventas, Caja, Supervisor, Administrador). Cobrar exige `cash.operate`. Cancelar pedidos ajenos exige `sales.void`. **No hacen falta permisos nuevos.**
- La venta guarda `salesperson` (quien hizo el pedido); `seller` sigue siendo quien cobró. Una venta directa en caja tiene `salesperson` = el cajero.

## Decisiones (equipo, 2026-10-16)
1. **Precio: el del pedido.** Es lo que el vendedor le dijo al cliente y queda congelado en cada línea. Si al cobrar es distinto al del catálogo, la venta se cobra igual y queda `needs_review`, así aparece en la bandeja de revisión que ya existe.
2. **Vencimiento: al final del día** (zona horaria de Bogotá). Los pedidos de hoy se cobran hoy; el código diario se reinicia sin riesgo de confusión.
3. **Código: número de 4 dígitos** (1000–9999), único entre los pedidos del día, para dictarlo o anotarlo. Sin impresora por ahora.
4. **Stock: solo avisar.** El vendedor ve "bajo el mínimo" o "sin existencias" y decide. Al cobrar rige la regla de siempre: en línea no se vende sin stock.

## Fuera de esta spec
Cotizaciones con validez y formato para el cliente, impresión de tiquetes, comisiones por vendedor y reportes. Los reportes podrán usar `salesperson` cuando lleguen.

## Criterios de aceptación
- Un usuario con solo el rol **Ventas** puede crear un pedido, pero **no** cobrarlo (403).
- Cobrar un pedido produce una venta con `salesperson` = vendedor y `seller` = cajero. El stock baja una sola vez.
- Cobrar el mismo pedido dos veces, incluso con reintentos simultáneos, deja una sola venta.
- Un pedido `CANCELADO` o `VENCIDO` no se puede cobrar. Un pedido de ayer cuenta como vencido aunque nadie haya cambiado su estado.
- Si el catálogo cambió de precio, se cobra el del pedido y la venta aparece en la bandeja de revisión.
- No hay dos pedidos pendientes con el mismo código el mismo día.
- El cajero puede cobrar menos de lo pedido (quitar líneas o bajar cantidades), pero no más.
