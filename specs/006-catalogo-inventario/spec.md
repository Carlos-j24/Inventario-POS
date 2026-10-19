# Spec 006 — Catálogo e inventario en la app

> Estado: ✅ **completada (2026-10-19)**. Tareas en tasks.md (T1–T9, PRs #46–#54). Decisiones delegadas por el equipo (PR #44).

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
- Flujo: **borrador → pendiente de aprobación → aprobado** (genera los movimientos `ADJUSTMENT`) **o rechazado** (no mueve nada, con motivo). Lo solicita bodega y lo aprueba quien tiene `inventory.adjust` (decisión 1).

### Conteos físicos
- Se abre un conteo para **una bodega**, completa o filtrada por **categoría**, y queda la lista de productos a contar.
- **Conteo ciego**: quien cuenta no ve la existencia del sistema ni la diferencia; solo escribe lo que hay. Quien aprueba (con `inventory.adjust`) ve contado, esperado, diferencia y su valor al costo promedio.
- La diferencia se calcula contra la existencia **en el momento en que se contó cada línea**, para que la caja pueda seguir vendiendo durante el conteo (constitución, principio 3): esperado = movimientos hasta la hora en que se contó la línea (decisión 3).
- Flujo: **abierto → contado (enviado a aprobación) → aprobado** (cada diferencia distinta de cero genera un `ADJUSTMENT` con motivo "conteo físico") **o anulado** (no mueve nada).
- Un conteo aprobado puede dejar stock negativo si después del conteo hubo ventas sin conexión: se acepta y se marca `needs_review`, como en las ventas.
- Solo un conteo abierto a la vez por bodega y producto.

### Traslados
- De una bodega activa a **otra distinta**. Las cantidades salen como `TRANSFER_OUT` en el origen y entran como `TRANSFER_IN` en el destino.
- La salida va al costo promedio del origen y **la entrada lleva ese mismo costo** al destino (`unit_cost`), para que el inventario valorizado total no cambie por mover mercancía.
- Un traslado no puede dejar en negativo la bodega de origen.
- **Un solo paso**: la salida y la entrada se registran juntas al confirmar (decisión 4).

## Lo que cambia en el backend
- **Permisos** (migración de datos, como `0004_reports_costs_permission`): `inventory.transfer` nuevo para Administrador, Jefe de bodega y Auxiliar de bodega (decisión 5). Los demás ya existen.
- **`catalog/services.py`** (nuevo): crear y editar productos, presentaciones y categorías con las reglas de arriba; historial de precios (`PriceChange`).
- **API de catálogo**: hoy `GET /api/catalog/products/` solo lista los activos para el POS y no pide permiso. Se mantiene igual para el POS y se añaden:
  - `GET /api/catalog/admin/products/` (búsqueda, filtro por categoría y activo/inactivo), `POST`, `GET/PATCH …/<id>/` con `catalog.edit`; los campos de precio exigen además `catalog.edit_prices` (403 si no lo tiene).
  - Presentaciones dentro del producto; `GET/POST/PATCH /api/catalog/categories/`; `GET /api/catalog/units/`.
  - `GET …/<id>/price-history/`.
- **`apps/inventory`**: modelos `Adjustment`/`AdjustmentLine`, `PhysicalCount`/`CountLine` y `Transfer`/`TransferLine`, con su servicio y su API (`/api/inventory/adjustments/`, `/counts/`, `/transfers/`, con acciones `submit`, `approve`, `reject`, `void`, `receive` según el documento). El serializer del conteo **no devuelve** la existencia esperada a quien solo tiene `inventory.count`.
- **Admin de Django**: el precio del producto pasa a solo lectura (para que todo cambio de precio quede en el historial) y los documentos nuevos solo se consultan.
- **Ventas sin conexión de un producto desactivado**: hoy `SaleLineInputSerializer` solo acepta productos activos, así que una venta hecha sin conexión antes de desactivar el producto **se rechaza al sincronizar** (400). Pasa a aceptarse y marcarse `needs_review` (decisión 6); la venta en línea sigue exigiendo producto activo.

## Lo que cambia en el frontend
- **Productos** (`pages/Products.tsx`): lista con búsqueda por SKU, nombre o código de barras, filtro por categoría y activos/inactivos; formulario de producto con presentaciones y códigos; el precio solo se puede editar con `catalog.edit_prices` (sin él se ve, pero bloqueado); historial de precios. El dinero en centavos enteros (`money.ts`).
- **Ajustes** (`pages/Adjustments.tsx`): crear un ajuste con líneas (producto, unidad, cantidad, entra o sale), motivo y nota; bandeja de pendientes para aprobar o rechazar.
- **Conteos** (`pages/Counts.tsx`): abrir un conteo (bodega y categoría), pantalla de conteo ciego con búsqueda y lector de código de barras (el lector actúa como teclado, igual que en la caja), y vista de aprobación con diferencias y su valor (el valor solo con `reports.costs`).
- **Traslados** (`pages/Transfers.tsx`): origen, destino y líneas; lista de traslados.
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

## Decisiones (2026-10-18)
El equipo delegó las ocho decisiones; se tomaron las opciones más simples que respetan la constitución (kardex auditable, la caja nunca se detiene, nada de negativos ocultos). Las alternativas descartadas siguen abiertas para una spec posterior si un cliente las necesita.

1. **Ajustes: los pide bodega y los aprueba quien tiene `inventory.adjust`.** Lo solicita quien tiene `inventory.receive` o `inventory.count` (el auxiliar es quien encuentra la mercancía dañada); quien tiene `inventory.adjust` puede crear y aprobar los suyos, para no bloquear a una ferretería donde el dueño está solo. Queda registrado quién pidió y quién aprobó. Un tope por valor para exigir otra firma queda para después.
2. **Producto creado sin `catalog.edit_prices`: queda inactivo, "pendiente de precio".** Bodega lo registra cuando llega la mercancía; quien tiene el permiso le pone precio y lo activa. Ningún producto se vende con un precio que no puso quien debía. La **tarifa de IVA y el excluido** también exigen `catalog.edit_prices`, porque cambian lo que se declara a la DIAN.
3. **Diferencia del conteo: esperado a la hora en que se contó cada línea.** Al aprobar, esperado = suma de los movimientos de ese producto y bodega con `occurred_at` hasta la hora de la línea; ajuste = contado − esperado. La caja sigue vendiendo durante el conteo. Para el riesgo de ventas sin conexión que lleguen después de aprobar: al aprobar se avisa si hay cajas de esa bodega con ventas por sincronizar, y toda venta que llegue con fecha anterior a un conteo aprobado del mismo producto y bodega se marca `needs_review`.
4. **Traslados en un solo paso.** Salida y entrada juntas al confirmar, en una transacción: no hay mercancía "en tránsito" fuera del inventario valorizado. La base de demostración tiene una sola bodega; **confirmar con la ferretería** que sus bodegas están en el mismo sitio. Si un cliente tiene sedes separadas, los dos pasos (despachar y recibir) van en otra spec.
5. **Permiso nuevo `inventory.transfer`**, por migración de datos, para Administrador, Jefe de bodega y Auxiliar de bodega. Mover mercancía no es comprar ni dar de baja, y así el administrador decide quién lo hace sin dar permisos de más.
6. **Venta sin conexión de un producto desactivado: se acepta y queda para revisión** (`needs_review`, con el precio cobrado). La venta ya ocurrió y el cliente se llevó la mercancía; rechazarla descuadraría inventario y caja. La venta en línea sigue exigiendo producto activo.
7. **Productos que nadie contó: no generan ajuste.** Antes de aprobar se muestra la lista "sin contar" y el aprobador puede marcarlos en 0, uno por uno o todos, de forma explícita. Contarlos como 0 por omisión daría de baja mercancía que solo se olvidó contar.
8. **Motivos de ajuste: lista fija en el código** (daño, pérdida o robo, uso interno, vencimiento o mal estado, error de registro, sobrante, conteo físico) con nota obligatoria. Así los reportes de pérdidas siguen siendo comparables; la nota cubre los casos raros.
