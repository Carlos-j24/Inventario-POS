# Spec 013 — Versión sencilla (taller pequeño)

> Estado: ✅ **completada (2026-11-03)**: aprobada en el PR #99, T1 a T7 en los PRs #100 a #106. Decisiones tomadas con Carlos el 2026-11-03. Tareas en tasks.md.

## Problema
Arias pidió (2026-11-03) que la app sea **lo más sencilla posible**: el taller es pequeño y necesita
- control de inventario: entradas, y las salidas que hace cada venta;
- ingreso de motos;
- ventas e impresión de la factura;
- ver cada día, semana y mes cuánto se vendió, cuánto dejó el taller, cuánto el lavadero y la ganancia.

Hoy el administrador ve 19 pestañas (Caja, Órdenes, Mis órdenes, Motos, Pedidos, Cotizaciones, Entradas, Existencias, Productos, Mantenimientos, Conteos, Ajustes, Traslados, Ventas, Revisión, Reportes, DIAN, Usuarios y Roles), pensadas para una ferretería con vendedores, varias bodegas y supervisores. Además, faltan dos cosas que piden:
- no hay un resumen por día, semana o mes que separe repuestos, taller y lavadero;
- no se pueden anotar los gastos para sacar la ganancia real.

## Objetivo
Una **versión sencilla** que cada instalación activa con una casilla. Muestra solo lo que usa un taller pequeño, cobra las órdenes de trabajo sin pasos de aprobación, imprime la venta en hoja carta con el logo y da un resumen de ingresos, gastos y ganancia por día, semana y mes.

## Reglas
1. **Casilla "Versión sencilla"** en los datos del negocio (admin de Django), apagada por defecto. La ferretería y cualquier instalación que no la active quedan exactamente igual.
2. **Pantallas ocultas** con la casilla: Pedidos, Cotizaciones, Conteos, Ajustes, Traslados, Revisión, Roles, DIAN y Mis órdenes. Quedan Caja, Órdenes, Motos, Entradas, Existencias, Productos, Mantenimientos, Ventas, Gastos (nueva), Reportes y Usuarios, cada una con los permisos de siempre. Ocultar una pantalla no borra datos ni permisos: al apagar la casilla vuelve todo como estaba.
3. **Usuarios con roles fijos**: con la pantalla Roles oculta, Usuarios solo ofrece los roles que ya existen.
4. **Orden simplificada**: con la casilla, las órdenes de trabajo saltan la aprobación del cliente.
   - Lo que se agrega a la orden queda aprobado al instante y la orden no pasa por "Esperando aprobación".
   - El mecánico asignado es opcional.
   - El flujo es: recibir la moto (placa, km, qué pide), agregar repuestos y mano de obra, marcarla lista, cobrar en caja y entregar.
   - Los repuestos siguen saliendo del inventario al agregarlos, como hoy.
5. **Factura en hoja carta**: toda venta se puede imprimir (o guardar en PDF) en hoja carta, desde la caja al cobrar y desde Ventas. Lleva:
   - el logo y los datos del negocio;
   - número y fecha;
   - el cliente, si se eligió;
   - la moto y la orden, si viene de una orden;
   - las líneas con cantidad, precio y total, el IVA y el total;
   - la forma de pago y quién cobró.

   No es factura electrónica: se titula "Comprobante de venta" y lleva la leyenda "Documento sin validez fiscal" (decisión 6). Usa la misma maqueta de impresión de las cotizaciones (`QuotePrint`).
6. **Línea de ingreso** de cada producto: Repuestos, Taller o Lavadero.
   - Un producto con inventario siempre es Repuestos.
   - Un servicio (spec 010) es Taller o Lavadero; se elige en Productos y por defecto es Taller.
   - La venta guarda la línea de cada renglón, como ya guarda `is_service`, así el resumen no cambia si después se recategoriza el producto.
7. **Gastos**: pantalla nueva para anotar los gastos del negocio (arriendo, sueldos, servicios públicos, jabón y otros). Cada gasto lleva:
   - fecha y valor;
   - una categoría de una lista corta que el administrador edita;
   - una nota opcional;
   - quién lo anotó.

   Se corrige o se anula dejando rastro, nunca se borra. Un gasto marcado "Pagado de la caja" se anota como salida de efectivo del turno abierto y se resta del arqueo (decisión 7). Los gastos los maneja quien tiene el permiso nuevo `expenses.manage`, que de entrada solo tiene el Administrador (decisión 8).
8. **Resumen** (pestaña nueva y primera en Reportes) por **día, semana o mes**, con el selector de periodo de siempre. Muestra:
   - **Ingresos** por línea (Repuestos, Taller, Lavadero) y en total, ya restadas las devoluciones;
   - **Costo de los repuestos** vendidos (costo promedio, spec 004);
   - **Ganancia bruta**: ingresos menos el costo de los repuestos;
   - **Gastos** del periodo, por categoría;
   - **Ganancia neta**: ganancia bruta menos gastos.

   Tiene una tabla por día, semana o mes según el rango, y se exporta a Excel (CSV) como los otros reportes. La ganancia y el costo solo los ve quien tiene `reports.costs`, como Márgenes.
9. **Demo**: `seed_demo --taller` activa la versión sencilla, marca los lavados como Lavadero y la mano de obra como Taller, y siembra un mes de gastos. La demo de la ferretería queda igual.
10. Sin librerías nuevas.

## Decisiones (2026-11-03, con Carlos)
1. **Se ocultan** Pedidos, Cotizaciones, Conteos, Ajustes, Traslados, Revisión y Roles; DIAN también, porque salió del plan del taller. **Se quedan** Mantenimientos y el historial de cada moto.
2. **Ingreso de motos con orden simplificada**: recibir, agregar repuestos y mano de obra, y cobrar, sin aprobación del cliente ni pantalla del mecánico. _Descartado:_ la orden completa de hoy, o solo registrar la moto y cobrar todo en caja.
3. **Factura impresa en hoja carta con logo, sin DIAN.** _Descartado:_ solo la tirilla, o volver a meter la factura electrónica.
4. **La ganancia resta los gastos**: hace falta la pantalla de Gastos. _Descartado:_ solo venta menos costo.
5. **Una casilla por instalación, no otro programa**: se mantiene un solo software (decisión del 2026-10-27), y el taller puede pasar a la versión completa el día que crezca.
6. **El impreso se titula "Comprobante de venta"** y dice "Documento sin validez fiscal": sin la DIAN, un papel que diga "Factura de venta" puede traerle problemas al taller. Carlos lo confirma con el contador del taller antes de la puesta en marcha.
7. **Un gasto pagado de la caja sale del arqueo**: la casilla "Pagado de la caja" lo anota como salida de efectivo del turno abierto, así el cajón cuadra.
8. **Permiso nuevo `expenses.manage`** para Gastos, solo para el Administrador al principio. _Descartado:_ reutilizar `reports.costs`, que es para ver costos y no para anotar dinero.

## Fuera de alcance
- Factura electrónica DIAN (spec 005), que sigue en el código pero oculta.
- Nómina, cuentas por pagar, proveedores y presupuesto: Gastos solo anota lo que salió.
- Comisiones de mecánicos y lavadores.
- Gráficas: el resumen es en tablas e indicadores.
- Arreglar el desborde en celular de la cabecera, Órdenes y Motos (pendiente aparte). Con menos pestañas, la cabecera ya se acorta.

## Criterios de aceptación
- Con la casilla activa, el administrador ve 11 pestañas y no ve Pedidos, Cotizaciones, Conteos, Ajustes, Traslados, Revisión, Roles, DIAN ni Mis órdenes. Al apagarla, vuelven todas.
- Una orden recibida con un aceite y la mano de obra se marca lista, se cobra en caja y se entrega, sin pasar por "Esperando aprobación". El aceite sale del inventario.
- Una venta con un repuesto, una mano de obra y un lavado se imprime en hoja carta con el logo, sus tres líneas, el IVA y el total, en una sola hoja y sin hojas en blanco (comprobado imprimiendo a PDF).
- Ejemplo de resumen de un día:
  - ventas: un aceite de $40.000 que costó $28.000, una mano de obra de $20.000 y dos lavados de $12.000;
  - gasto: $15.000 de jabón;
  - resultado: Repuestos $40.000, Taller $20.000, Lavadero $24.000, ingresos $84.000, costo $28.000, ganancia bruta $56.000, gastos $15.000 y ganancia neta $41.000.
- El mismo resumen por mes agrupa los días del mes, y por semana va de lunes a domingo.
- Una devolución resta de la línea de ingreso que corresponde, en el día de la devolución.
- La ferretería (sin la casilla) se ve y funciona igual que antes.
