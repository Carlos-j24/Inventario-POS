# Spec 006 — Catálogo e inventario en la app

> Estado: 📝 **borrador (2026-10-18)**. Las decisiones abiertas del final las responde el equipo en el PR antes de programar.

## Problema
Hoy los productos solo se crean y se editan en el **admin de Django**, que no es una herramienta para el día a día de una ferretería: no pide permisos de la app, no deja rastro de quién cambió un precio y deja editar cosas que rompen el inventario (la unidad base o el factor de una presentación con movimientos ya hechos).

Además, los permisos `catalog.edit`, `catalog.edit_prices`, `inventory.adjust` e `inventory.count` existen desde la spec 001 (y están en los roles por defecto), pero **no hay pantalla ni API que los use**. En la práctica:
- No hay forma de dar de baja mercancía dañada, perdida o de uso interno: el stock queda inflado y el inventario valorizado (spec 004) sobrevalora la bodega.
- No hay conteos físicos: las diferencias entre lo que dice el sistema y lo que hay en el estante solo se corrigen a mano en la base.
- Los tipos `TRANSFER_OUT` y `TRANSFER_IN` existen en `StockMovement`, pero nada los registra: no se puede pasar mercancía de la bodega al local.

Todo cliente necesita esto desde el primer día.

## Objetivo
Cuatro pantallas nuevas, cada una con su permiso y con la lógica en `services.py`:
1. **Productos** (`catalog.edit`; precios con `catalog.edit_prices`): crear y editar productos, categorías, presentaciones y códigos de barras, y activar o desactivar.
2. **Ajustes** (`inventory.adjust`): bajas por daño, pérdida o uso interno (y sobrantes), con motivo y aprobación.
3. **Conteos** (`inventory.count`): conteo ciego por bodega o categoría; las diferencias, al aprobarse, generan los ajustes.
4. **Traslados**: pasar mercancía entre bodegas con `TRANSFER_OUT` / `TRANSFER_IN`.

## Reglas
### Catálogo
- **SKU** obligatorio y único; no se cambia una vez el producto tiene movimientos (es el que sale en kardex, reportes y CSV).
- **Unidad base**: no se cambia si el producto tiene movimientos. Para manejarlo en otra unidad se crea un producto nuevo.
- **Presentaciones** (rollo = 100 m, caja = 50 und): factor mayor que cero; la unidad base no lleva presentación (ya lo valida `ProductUnit.clean`). Una presentación **usada** en ventas, pedidos o entradas no cambia de factor ni se borra: se desactiva y se crea otra. Motivo: una venta sin conexión en la cola se convierte al llegar con el factor vigente, y un factor nuevo cambiaría la cantidad descontada (y el precio, que hoy es precio base × factor).
- **Códigos de barras**: únicos entre productos **y** presentaciones juntos (hoy cada tabla es única por separado y un mismo código podría quedar en un producto y en la presentación de otro). Se valida en el servicio.
- **Precio de venta** con IVA incluido (regla del proyecto), en `Decimal`, mayor o igual a cero. Solo lo cambia quien tenga `catalog.edit_prices`. Cada cambio de precio queda en un **historial** (antes, después, usuario y fecha) que no se edita.
- **IVA**: tarifa 0 %, 5 % o 19 %; *excluido* (`vat_excluded`) solo con tarifa 0 % (restricción de la base, spec 005). Cambiar la tarifa no cambia el precio al público, solo cómo se separa la base del IVA en las ventas siguientes; las ventas pasadas conservan la suya.
- **Stock mínimo** mayor o igual a cero, en unidad base. Es lo que marca "Pedir" en Existencias y "bajo mínimo" en el inventario valorizado.
- **Activar y desactivar**: los productos no se borran (tienen kardex), se desactivan. Uno desactivado sale del catálogo del POS y de las búsquedas de entradas, pero sigue en el kardex, los reportes y el inventario valorizado mientras tenga existencias.
- **Categorías**: lista plana. Se crean y renombran; solo se borra una categoría sin productos.
- El **costo** no se edita en el catálogo: es el promedio ponderado que mantiene `record_movement` (spec 004).

### Movimientos de inventario (ajustes, conteos y traslados)
- Todo pasa por `record_movement`. Ningún documento escribe `StockLevel`.
- Cada documento (ajuste, conteo, traslado) tiene número propio (`AJ-000001`, `CF-000001`, `TR-000001`), usuario, fechas y estado, y guarda el `client_uuid` de su creación para que un doble clic o un reintento no lo duplique. Sus movimientos llevan el número en `reference` y cada línea apunta a su movimiento.
- Un documento **aprobado o aplicado no se edita ni se borra** (constitución, principio 2). Un error se corrige con otro documento.
- Cantidades en la unidad que elija el usuario (rollo o metro) y se guardan en **unidad base**.
- Aprobar o aplicar un documento bloquea el documento (`select_for_update`) y registra todos sus movimientos en **una sola transacción**: o entran todos o ninguno. Dos personas aprobando a la vez no lo aplican dos veces.
- Todo esto exige conexión, como las entradas.

### Ajustes
- **Motivos**: daño, pérdida o robo, uso interno, vencimiento o mal estado, error de registro y sobrante. Nota obligatoria.
- Una **baja** (salida) sale al **costo promedio vigente** (lo hace `record_movement`) y **no puede dejar el stock en negativo**.
- Un **sobrante** (entrada) entra al costo promedio vigente. Si el producto no tiene costo (promedio en 0, nunca ha entrado), hay que indicar el costo de la entrada.
- Flujo: **borrador → pendiente de aprobación → aprobado** (genera los movimientos `ADJUSTMENT`) **o rechazado** (no mueve nada, con motivo). Quién solicita y quién aprueba: decisión 1.

### Conteos físicos
- Se abre un conteo para **una bodega**, completa o filtrada por **categoría**, y queda la lista de productos a contar.
- **Conteo ciego**: quien cuenta no ve la existencia del sistema ni la diferencia; solo escribe lo que hay. Quien aprueba (con `inventory.adjust`) ve contado, esperado, diferencia y su valor al costo promedio.
- La diferencia se calcula contra la existencia **en el momento en que se contó cada línea**, para que la caja pueda seguir vendiendo durante el conteo (constitución, principio 3). Cómo calcularla: decisión 3.
- Flujo: **abierto → contado (enviado a aprobación) → aprobado** (cada diferencia distinta de cero genera un `ADJUSTMENT` con motivo "conteo físico") **o anulado** (no mueve nada).
- Un conteo aprobado puede dejar stock negativo si después del conteo hubo ventas sin conexión: se acepta y se marca `needs_review`, como en las ventas.
- Solo un conteo abierto a la vez por bodega y producto.

### Traslados
- De una bodega activa a **otra distinta**. Las cantidades salen como `TRANSFER_OUT` en el origen y entran como `TRANSFER_IN` en el destino.
- La salida va al costo promedio del origen y **la entrada lleva ese mismo costo** al destino (`unit_cost`), para que el inventario valorizado total no cambie por mover mercancía.
- Un traslado no puede dejar en negativo la bodega de origen.
- Si es en uno o dos pasos (con mercancía en tránsito): decisión 4.

## Lo que cambia en el backend
- **Permisos** (migración de datos, como `0004_reports_costs_permission`): según la decisión 5, `inventory.transfer` nuevo y asignado a los roles por defecto que se acuerden. Los demás ya existen.
- **`catalog/services.py`** (nuevo): crear y editar productos, presentaciones y categorías con las reglas de arriba; historial de precios (`PriceChange`).
- **API de catálogo**: hoy `GET /api/catalog/products/` solo lista los activos para el POS y no pide permiso. Se mantiene igual para el POS y se añaden:
  - `GET /api/catalog/admin/products/` (búsqueda, filtro por categoría y activo/inactivo), `POST`, `GET/PATCH …/<id>/` con `catalog.edit`; los campos de precio exigen además `catalog.edit_prices` (403 si no lo tiene).
  - Presentaciones dentro del producto; `GET/POST/PATCH /api/catalog/categories/`; `GET /api/catalog/units/`.
  - `GET …/<id>/price-history/`.
- **`apps/inventory`**: modelos `Adjustment`/`AdjustmentLine`, `PhysicalCount`/`CountLine` y `Transfer`/`TransferLine`, con su servicio y su API (`/api/inventory/adjustments/`, `/counts/`, `/transfers/`, con acciones `submit`, `approve`, `reject`, `void`, `receive` según el documento). El serializer del conteo **no devuelve** la existencia esperada a quien solo tiene `inventory.count`.
- **Admin de Django**: el precio del producto pasa a solo lectura (para que todo cambio de precio quede en el historial) y los documentos nuevos solo se consultan.
- **Ventas sin conexión de un producto desactivado**: hoy `SaleLineInputSerializer` solo acepta productos activos, así que una venta hecha sin conexión antes de desactivar el producto **se rechaza al sincronizar** (400). Decisión 6.

## Lo que cambia en el frontend
- **Productos** (`pages/Products.tsx`): lista con búsqueda por SKU, nombre o código de barras, filtro por categoría y activos/inactivos; formulario de producto con presentaciones y códigos; el precio solo se puede editar con `catalog.edit_prices` (sin él se ve, pero bloqueado); historial de precios. El dinero en centavos enteros (`money.ts`).
- **Ajustes** (`pages/Adjustments.tsx`): crear un ajuste con líneas (producto, unidad, cantidad, entra o sale), motivo y nota; bandeja de pendientes para aprobar o rechazar.
- **Conteos** (`pages/Counts.tsx`): abrir un conteo (bodega y categoría), pantalla de conteo ciego con búsqueda y lector de código de barras (el lector actúa como teclado, igual que en la caja), y vista de aprobación con diferencias y su valor (el valor solo con `reports.costs`).
- **Traslados** (`pages/Transfers.tsx`): origen, destino y líneas; lista de traslados (y de pendientes por recibir si son de dos pasos).
- Las pestañas aparecen según los permisos, como hoy (`App.tsx`). La lógica que se pueda probar sin React va en archivos aparte (por ejemplo, la conversión de unidades y la validación de líneas).
- Ninguna de estas pantallas funciona sin conexión: muestran el aviso y no encolan nada.

## Fuera de esta spec
- Precio propio por presentación (el rollo más barato que 100 m sueltos); hoy es precio base × factor.
- Varios códigos de barras por producto o presentación.
- Importar productos desde Excel o CSV.
- Proveedores y órdenes de compra; costo de reposición.
- Conteos o ajustes sin conexión, y conteo con la cámara del celular.
- Lotes, vencimientos y seriales (droguería).
- Reporte de pérdidas por bajas (se puede sacar del kardex; podría ir en una spec de reportes).
- Imágenes de producto.

## Criterios de aceptación (propuestos)
- Quien tiene `catalog.edit` crea un producto con categoría, unidad base, presentación "rollo = 100 m" y código de barras, y aparece en la caja tras actualizar el catálogo.
- Sin `catalog.edit_prices`, la API responde 403 al intentar cambiar el precio y la pantalla no deja editarlo; con él, el cambio queda en el historial con usuario y fecha.
- No se puede cambiar la unidad base ni el factor de una presentación con movimientos; tampoco repetir un código de barras entre un producto y la presentación de otro.
- Excluido de IVA con tarifa distinta de 0 % se rechaza.
- Un producto desactivado desaparece del POS pero sigue en el kardex, en Existencias y en el inventario valorizado.
- Una baja de 3 martillos con promedio $20.000 deja 3 unidades menos, un `ADJUSTMENT` de −3 a $20.000 y el inventario valorizado $60.000 más bajo; no puede dejar el stock en negativo.
- Un ajuste rechazado no mueve inventario; uno aprobado no se puede editar ni aprobar dos veces (ni con dos aprobaciones a la vez, probado en PostgreSQL).
- En un conteo ciego, la API no le devuelve la existencia esperada a quien solo tiene `inventory.count`.
- Hay 10 m de cable, se cuentan 8 y después se venden 2: al aprobar, el ajuste es −2 (no −4) y quedan 6.
- Un traslado de 5 unidades de BOD a LOC deja −5 en BOD y +5 en LOC con el mismo costo unitario, y el inventario valorizado total no cambia.
- La suma de los movimientos de cada producto y bodega sigue cuadrando con `StockLevel` después de ajustes, conteos y traslados.
- Un usuario sin el permiso de cada pantalla no la ve y la API le responde 403.

## Decisiones abiertas para el equipo
Cada una con opciones y una recomendación. Responder en el PR.

1. **¿Quién solicita y quién aprueba un ajuste?**
   - a) Solo quien tiene `inventory.adjust`, que lo crea y lo aplica en un paso.
   - b) Lo solicita quien tiene `inventory.receive` o `inventory.count` (auxiliar de bodega) y lo aprueba quien tiene `inventory.adjust`; quien tiene `inventory.adjust` puede aprobar los suyos, y queda registrado quién lo pidió y quién lo aprobó.
   - c) Como b), pero nadie aprueba sus propios ajustes.
   - **Recomendación: b).** El auxiliar es quien encuentra la mercancía dañada, así que debe poder reportarla, y la baja sigue necesitando a alguien con `inventory.adjust`. Prohibir la autoaprobación (c) bloquea a una ferretería pequeña donde el dueño está solo; si se quiere control, se puede añadir después un tope por valor.

2. **Precio de un producto creado por alguien sin `catalog.edit_prices`** (el Jefe de bodega tiene `catalog.edit` pero no ese permiso).
   - a) No puede crear productos: crear exige los dos permisos.
   - b) Lo crea sin precio y el producto queda **inactivo** ("pendiente de precio") hasta que alguien con `catalog.edit_prices` le pone precio y lo activa.
   - c) Lo crea con el precio que quiera, y solo los cambios posteriores exigen el permiso.
   - **Recomendación: b).** Bodega puede registrar lo que llega sin esperar al dueño, y ningún producto se vende sin un precio que haya puesto quien tiene el permiso. ¿La **tarifa de IVA** también exige `catalog.edit_prices`? Se recomienda que sí: cambia lo que se declara a la DIAN.

3. **Cómo se calcula la diferencia de un conteo mientras se sigue vendiendo.**
   - a) Bloquear ventas y movimientos de la bodega mientras haya un conteo abierto.
   - b) Foto de las existencias al abrir el conteo: diferencia = contado − foto. Falla si se vende durante el conteo.
   - c) Al guardar cada línea se registra la hora en que se contó; al aprobar, el esperado es la suma de los movimientos de ese producto y bodega con `occurred_at` hasta esa hora, y el ajuste es contado − esperado. Lo que se movió después del conteo queda tal cual.
   - **Recomendación: c).** No detiene la caja (principio 3) y usa `occurred_at`, así que una venta sin conexión que se hizo antes del conteo pero llegó después, si llega antes de aprobar, se cuenta bien. Riesgo: si llega **después** de aprobar, la diferencia queda contada dos veces; se mitiga mostrando al aprobar si hay cajas de esa bodega con ventas por sincronizar y marcando `needs_review` cualquier venta que llegue con fecha anterior a un conteo aprobado. Se pide contar y guardar por estante, no al final del día.

4. **Traslados en uno o en dos pasos.**
   - a) Un paso: la salida y la entrada se registran juntas al confirmar.
   - b) Dos pasos: el origen despacha (`TRANSFER_OUT`, mercancía "en tránsito") y el destino recibe (`TRANSFER_IN`), y puede recibir menos (la diferencia queda como faltante para un ajuste).
   - **Recomendación: a) por ahora**, si las bodegas del primer cliente están en el mismo sitio (bodega de atrás y mostrador): es más simple y no hay mercancía "en el aire" que no esté en ninguna bodega del inventario valorizado. Si hay sedes separadas, b). Confirmar cómo es la ferretería.

5. **Permiso para traslados.**
   - a) Usar `inventory.receive` (quien registra entradas).
   - b) Usar `inventory.adjust`.
   - c) Permiso nuevo `inventory.transfer`, por migración, para Administrador, Jefe de bodega y Auxiliar de bodega.
   - **Recomendación: c).** Un traslado no es una entrada de compra ni una baja; con un permiso propio el administrador puede decidir quién mueve mercancía sin dar más de la cuenta. Es un cambio en el modelo de permisos, por eso se pregunta.

6. **Venta sin conexión de un producto que se desactivó mientras tanto.**
   - a) Se rechaza al sincronizar, como hoy (queda "rechazada" en la cola de la caja).
   - b) Se acepta (con el precio cobrado, como toda venta sin conexión) y se marca `needs_review` para que bodega la revise.
   - **Recomendación: b).** La venta ya ocurrió y el cliente se fue con la mercancía; rechazarla descuadra el inventario y la caja (principios 1 y 3). La venta en línea sigue exigiendo producto activo. Cambia lo que acepta `POST /api/sales/` con `offline=true`, por eso se pregunta.

7. **Productos de un conteo por bodega que nadie contó.**
   - a) Se ignoran: no generan ajuste.
   - b) Cuentan como 0.
   - **Recomendación: a)**, pero antes de aprobar se muestra la lista "sin contar" y el aprobador puede marcarlos en 0 uno por uno o todos a la vez. Contar como 0 por omisión daría de baja mercancía que solo se olvidó contar.

8. **Motivos de ajuste: lista fija o editable.**
   - a) Lista fija en el código (daño, pérdida o robo, uso interno, vencimiento o mal estado, error de registro, sobrante, conteo físico) más nota obligatoria.
   - b) Tabla editable por el administrador.
   - **Recomendación: a).** Los motivos sirven para reportes futuros y una lista fija los mantiene comparables; la nota cubre los casos raros.
