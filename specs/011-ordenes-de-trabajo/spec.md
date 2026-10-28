# Spec 011 — Órdenes de trabajo (módulo de taller, etapa 3)

> Estado: **aprobada (2026-10-28)** en el PR #81. Decisiones tomadas con Carlos el 2026-10-28. Tareas en tasks.md.

## Problema
Arias recibe motos para mantenimiento y reparación. Hoy la app sabe de clientes y motos (spec 009) y cobra servicios como la mano de obra (spec 010), pero no hay **orden de trabajo**. Faltan entonces:
- un comprobante de que la moto entró y en qué estado;
- qué se le va a hacer y cuánto cuesta;
- quién la está arreglando;
- qué repuestos se usaron;
- cuándo está lista y si ya se pagó y se entregó.

La propuesta (2026-10-25) incluye exactamente esto: ingreso de la moto y su estado, diagnóstico, cotización aprobada por el cliente, mecánico asignado, repuestos que se descuentan del inventario, mano de obra y salida con entrega. Es el módulo más grande de la propuesta (unas 90 horas).

## Objetivo
Llevar cada moto desde que entra hasta que sale:
1. recepción la recibe;
2. el mecánico la diagnostica y la arregla;
3. el cliente aprueba el presupuesto;
4. los repuestos salen de la bodega cuando se usan;
5. la caja cobra todo de una vez;
6. la moto se entrega solo si está pagada.

## Reglas
1. **Orden de trabajo** (`OT-000001`):
   - la moto (spec 009) y su dueño al momento del ingreso;
   - el kilometraje de llegada, que actualiza el de la moto;
   - lo que pide el cliente;
   - el estado en que llega: rayones, golpes, lo que falta y lo que deja (casco, documentos), escrito por recepción;
   - el mecánico asignado y el diagnóstico;
   - las fechas de cada paso.
2. **Estados**:
   - **Recibida** → **Esperando aprobación** → **En reparación** → **Lista** → **Entregada**;
   - además, **Cancelada** desde cualquier estado antes de Entregada.

   Cada cambio queda con quién y cuándo.
3. **Presupuesto**: líneas de repuestos (productos con inventario) y de mano de obra (servicios, spec 010).
   - Los repuestos van al precio del catálogo.
   - La mano de obra lleva el precio que pone recepción para ese trabajo.
   - Se imprime con la hoja de las cotizaciones (spec 007).
4. **Aprobación del cliente**: la registra recepción, con quién aprobó y cómo (en persona o por llamada), la fecha y el total aprobado.
   - Lo que se agrega después de aprobado queda **por aprobar**.
   - Lo que está por aprobar no se cobra ni se saca de la bodega hasta una nueva aprobación.
5. **Repuestos**:
   - salen de la **bodega principal** cuando se sacan para la moto, ya aprobados, con un movimiento nuevo "Salida a orden de trabajo" y la referencia de la orden;
   - si no se usan o la orden se cancela, vuelven con "Regreso de orden de trabajo";
   - el inventario es exacto aunque la moto pase días en el taller.
6. **Mecánico**: rol nuevo "Mecánico" con el permiso `workshop.repair`. Ve las órdenes que tiene asignadas y puede:
   - escribir el diagnóstico;
   - agregar repuestos y mano de obra (sin tocar precios);
   - sacar los repuestos aprobados;
   - marcar la orden **Lista**.
7. **Recepción** (`workshop.receive`):
   - recibe la moto y asigna el mecánico;
   - pone el precio de la mano de obra;
   - registra la aprobación;
   - manda la orden a la caja y la entrega.
8. **Cobro**:
   - una orden Lista se manda a la caja como un **pedido** del día (spec 002), con su código de 4 dígitos;
   - la caja la cobra como cualquier pedido, a los precios aprobados y sin dejar la venta para revisión por precio;
   - los repuestos no se descuentan otra vez: la venta usa los movimientos que ya hizo la orden.
9. **Entrega**: solo con la orden **cobrada**. Al entregar se registra quién la entregó, cuándo y el kilometraje de salida, si cambió.
10. **Anular la venta de una orden**:
    - la orden vuelve a **Lista**, por cobrar otra vez;
    - el inventario no se mueve, porque los repuestos siguen puestos en la moto;
    - si hay que devolver repuestos, se hace una devolución de la venta (spec 001).
11. Una moto no puede tener dos órdenes abiertas a la vez. La ficha de la moto (spec 009) muestra sus órdenes.
12. Todo esto solo con el **módulo de taller activo** (spec 009); apagado, la API de órdenes responde 404.
13. `seed_demo --taller` siembra:
    - un mecánico;
    - órdenes en todos los estados, una con un cambio sin aprobar y una cancelada con su repuesto devuelto.

    La ferretería queda igual.
14. Sin librerías nuevas.

## Decisiones (2026-10-28)
1. **Los repuestos salen de la bodega al sacarlos para la moto**, no al cobrar. Así el inventario es exacto mientras la moto está en el taller, y si no se usan vuelven.
   - _Descartado:_ descontarlos al cobrar (más simple, pero muestra en bodega repuestos que ya están instalados).
2. **Recepción registra la aprobación del presupuesto**: quién aprobó y cómo, con la hoja de las cotizaciones para mostrar o imprimir. Si el trabajo cambia, se pide una nueva aprobación.
   - _Descartado:_ la firma del cliente en pantalla (solo sirve si está presente).
3. **Sin fotos de ingreso por ahora**: el estado de la moto se escribe. La propuesta las incluía y quedan para cuando Arias las pida.
   - _Descartado por ahora:_ fotos con la cámara del celular guardadas en el servidor.
4. **El mecánico entra al sistema y lleva sus órdenes**: diagnóstico, repuestos y mano de obra, y marca "lista". Recepción asigna, pone precios, cobra y entrega.
   - Sin comisiones por ahora: es una de las preguntas abiertas de la propuesta.
   - _Descartado:_ que el mecánico no use el sistema.

## Fuera de alcance
- Fotos de ingreso (decisión 3).
- Comisiones de los mecánicos.
- Avisos por WhatsApp (la propuesta no los incluye).
- Ventas a crédito.
- Historial de trabajos por moto y recordatorios de mantenimiento: spec 012.
- Factura electrónica de la orden: la venta de la orden ya pasa por la DIAN como cualquier venta (spec 005, T7 y T8).

## Criterios de aceptación
- **Ingreso**: Diana recibe la Boxer `XYZ12A` de Jorge con 15.400 km, "cambio de aceite y revisar frenos" y "rayón en el tanque, deja el casco". La moto queda con 15.400 km y la orden **Recibida**, asignada a un mecánico.
- **Diagnóstico y aprobación**:
  - el mecánico escribe el diagnóstico y agrega aceite, pastillas y la mano de obra;
  - Diana le pone precio a la mano de obra, imprime el presupuesto y registra que Jorge lo aprobó por llamada;
  - la orden pasa a **En reparación**.
- **Repuestos**:
  - al sacar el aceite y las pastillas, bajan de la bodega principal con la referencia de la orden;
  - un repuesto agregado después de aprobar no se puede sacar hasta una nueva aprobación.
- **Cobro**:
  - el mecánico marca la orden **Lista** y Diana la manda a la caja;
  - la caja la cobra por el código del pedido a los precios aprobados;
  - el inventario no baja otra vez;
  - no se puede entregar antes de cobrar.
- **Entrega**: después de cobrar, Diana entrega la moto y la orden queda **Entregada**.
- **Cancelación**: una orden cancelada devuelve a la bodega los repuestos que ya había sacado.
- **Anulación**: anular la venta de una orden la deja otra vez **Lista**, sin mover el inventario.
- **Permisos**:
  - un mecánico no ve las órdenes de otro ni cambia precios;
  - sin el módulo de taller, nada de esto aparece.
