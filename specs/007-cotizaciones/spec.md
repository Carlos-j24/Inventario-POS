# Spec 007 — Cotizaciones

> Estado: **aprobada (PR #56, 2026-10-19)**. Tareas en tasks.md.

## Problema
En una ferretería se cotiza todo el tiempo: el maestro de obra o el cliente llega con una lista de materiales ("20 bultos de cemento, 6 de arena, 50 m de cable…"), pide precios, se lleva la cotización impresa o por WhatsApp, la compara con otras ferreterías y vuelve días después a comprar, a veces por partes, a medida que avanza la obra.

Hoy la app no tiene cómo hacerlo. El **pedido** (spec 002) sirve para pasar del mostrador a la caja en el mismo día: vence a medianoche, no va a nombre de nadie y no se imprime. Lo que hace hoy el vendedor es anotar la lista a mano o en una hoja de cálculo, y al volver el cliente tiene que buscar todo de nuevo.

## Objetivo
El vendedor arma una **cotización** a nombre del cliente, con vigencia y en un formato para entregarle. Cuando el cliente vuelve, la cotización se busca por número o por nombre y **se convierte en pedido** con un clic; la caja la cobra como cualquier pedido. Así queda registro de lo cotizado y de cuánto se convirtió en venta.

## Flujo
```
Vendedor (Ventas)                            Cliente                        Vendedor            Cajero
arma la cotización ──▶ COT-000045 ──▶ se la lleva (impresa o PDF) ──▶ vuelve ──▶ la busca ──▶ pedido 4821 ──▶ cobra ──▶ venta
   │                                                                                │
   └── puede duplicarla o anularla                                                   └── puede convertir solo una parte
```

## Historias
1. **Como vendedor** armo la cotización con el buscador de productos o el lector (unidad y cantidad, como en el pedido), le pongo el nombre y el teléfono del cliente (o elijo un cliente registrado) y una nota ("entrega en obra, calle 12"). Veo el total con IVA.
2. **Como vendedor** la imprimo o la guardo como PDF desde el navegador, en una hoja con los datos de la ferretería (los de `Business`, spec 005), el número `COT-…`, la fecha, la vigencia, el cliente, las líneas con precio unitario y total, el IVA por tarifa y el total.
3. **Como vendedor** busco cotizaciones por número, por nombre o teléfono del cliente, y por estado (vigentes, vencidas, convertidas, anuladas). Veo las mías; el supervisor y el administrador ven todas.
4. **Como vendedor** convierto una cotización vigente en **pedido** (spec 002) y le doy al cliente el código de 4 dígitos para la caja. La caja la cobra como cualquier pedido.
5. **Como vendedor** duplico una cotización (por ejemplo, una vencida) para hacer una nueva con los precios de hoy.
6. **Como administrador** veo en Reportes cuánto se cotizó y cuánto se convirtió en venta, por vendedor.

## Reglas
- La cotización **no mueve inventario ni reserva existencias**. Al convertirla en pedido aparecen los avisos de stock del pedido ("bajo el mínimo", "sin existencias"); al cobrar rige la regla de siempre.
- Número propio `COT-000001`, `client_uuid` para que un doble clic no la duplique, quién la hizo y cuándo.
- Estados: `VIGENTE` → `CONVERTIDA` | `VENCIDA` | `ANULADA`. Vencida = pasó su fecha de vigencia, aunque nadie haya cambiado el estado (como los pedidos de ayer).
- **No se edita**: para cambiarla se duplica y se anula la anterior. Lo que el cliente tiene impreso es lo que quedó guardado.
- Cada línea guarda el precio cotizado (IVA incluido) y la tarifa de IVA de ese momento.
- El cliente es un nombre y un teléfono escritos a mano (el maestro de obra no siempre da su cédula) o, si se elige, un cliente registrado (spec 005); al facturar se usa el registrado.
- Crear, ver las propias, duplicar, anular las propias y convertir exige `sales.create`. Ver y anular las de otros exige `sales.void` o `reports.view`. **No hacen falta permisos nuevos** (salvo lo que se decida sobre descuentos).
- Crear y convertir **exige conexión**, como los pedidos.

## Lo que cambia en el backend
- `apps/sales/quotes.py` (servicio) y modelos `Quote` / `QuoteLine` con `valid_until`, cliente (texto o `Customer`), nota, estado, quién la creó y quién la anuló. `Order.quote` (opcional) para saber de qué cotización salió un pedido.
- API `/api/quotes/` (listar con búsqueda y estado, crear), `…/<id>/` (detalle con los datos para imprimir), `…/<id>/void/`, `…/<id>/duplicate/`, `…/<id>/order/` (convierte en pedido; con líneas y cantidades si es parcial).
- `create_order` acepta líneas con el precio cotizado. Una venta que cobra un pedido de una cotización vigente con el precio cotizado **no** queda `needs_review` por diferencia de precio, porque ese precio ya lo dio el negocio.
- Reportes: `/api/reports/quotes/` con lo cotizado, lo convertido y la tasa de conversión, por vendedor y período.

## Lo que cambia en el frontend
- Pestaña **Cotizaciones** (`pages/Quotes.tsx`, lógica en `quote.ts`) con el mismo buscador de productos de Pedidos y Ajustes.
- Vista para imprimir (`QuotePrint`, hoja carta con `@media print`): sin librerías nuevas; "Guardar como PDF" lo hace el navegador.
- En Reportes, una pestaña o un bloque "Cotizaciones".

## Fuera de esta spec
Enviar la cotización por correo o por WhatsApp desde la app (por ahora el PDF se adjunta a mano), firma del cliente, anticipos y separados, precios por cliente o listas de precios, y comisiones por vendedor.

## Criterios de aceptación
- Un usuario con solo el rol **Ventas** crea, imprime y convierte una cotización, pero no la cobra (403 en caja).
- Una cotización no cambia el stock; el pedido tampoco; la venta sí, una sola vez.
- Una cotización vencida no se convierte (400), pero se puede duplicar con los precios de hoy.
- Si el catálogo subió después de cotizar, la venta de una cotización vigente se cobra al precio cotizado y no queda para revisión.
- Dos clics seguidos en "Guardar" o "Convertir" no crean dos cotizaciones ni dos pedidos.
- Se puede convertir por partes, varias veces; lo convertido nunca pasa de lo cotizado, y la cotización queda `CONVERTIDA` cuando no queda nada por convertir.
- La hoja impresa muestra los datos del negocio, el número, la vigencia y totales que cuadran con el servidor.

## Decisiones (equipo, 2026-10-19)
1. **Precio: el cotizado mientras esté vigente.** Es lo que se le dijo al cliente. La línea del pedido lleva el precio cotizado y la venta no queda para revisión por esa diferencia. Una cotización vencida no se convierte: se duplica con los precios de hoy. _Descartada:_ cobrar siempre el precio del día (la cotización perdería su valor ante el cliente).
2. **Vigencia por defecto: 8 días**, editable al crearla (de 1 a 30 días). Cemento, hierro y cable cambian de precio seguido; una vigencia larga arriesga vender por debajo del costo.
3. **Sin descuentos en esta spec.** Se cotiza al precio del catálogo y no hay permisos nuevos. Los descuentos (por línea o global, con un permiso y un tope que también respete la caja) quedan para otra spec si un cliente los pide.
4. **Compra por partes, hasta agotar lo cotizado.** La obra compra por etapas: cada conversión elige líneas y cantidades, nunca más de lo que queda por convertir de cada línea, y el pedido sale con el precio cotizado. Si un pedido de la cotización se cancela o vence sin cobrarse, esas cantidades vuelven a estar disponibles. La cotización queda `CONVERTIDA` cuando lo cobrado cubre todo lo cotizado.
