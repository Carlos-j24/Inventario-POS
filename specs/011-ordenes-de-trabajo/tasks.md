# Tareas — Spec 011

> Spec aprobada (PR #81, 2026-10-28). Decisiones en spec.md.

- [x] **T1** Backend, modelo:
  - `WorkOrder` con su número, moto, dueño, kilometraje, pedido del cliente, estado al recibir, mecánico, diagnóstico, estado y fechas;
  - `WorkOrderLine` con repuesto o mano de obra, cantidad, precio, si está aprobada y su movimiento al sacarla;
  - `WorkOrderApproval` con quién aprobó, cómo, cuándo y el total;
  - una sola orden abierta por moto.
  - Movimientos nuevos "Salida a orden de trabajo" y "Regreso de orden de trabajo".
  - Permiso `workshop.repair` y rol "Mecánico" en una migración.
  - Admin solo de lectura.

  (Reglas 1, 2, 6 y 11)
  - En `apps/workshop/models.py`:
    - `WorkOrder` con número `OT-000001` y el dueño al recibirla, que se queda aunque la moto cambie de dueño;
    - `WorkOrderLine` en unidad base, que copia `is_service` del producto;
    - `WorkOrderApproval` (en persona o por llamada) y `WorkOrderEvent` (cada cambio de estado).
  - Tres restricciones de la base de datos:
    - una orden abierta por moto (las abiertas son `WorkOrder.OPEN`);
    - solo sale de la bodega un repuesto aprobado;
    - solo vuelve lo que salió.
  - `WORKSHOP_OUT` sale y `WORKSHOP_RETURN` entra, con el mismo trato que las ventas y las devoluciones en `record_movement`.
  - La migración `accounts/0007` crea el rol "Mecánico" (solo `workshop.repair`) y le da ese permiso al Administrador.
  - En el admin las órdenes solo se consultan.
  - 9 tests y 12 fallos a propósito. Uno era equivalente: los métodos de solo lectura de las líneas sobraban, porque la orden ya es de solo lectura, y se quitaron.
- [x] **T2** Servicios:
  - recibir (actualiza el kilometraje de la moto);
  - asignar mecánico;
  - diagnosticar;
  - agregar y quitar líneas: el mecánico sin precio, recepción con precio de mano de obra;
  - registrar la aprobación: lo agregado después queda por aprobar;
  - sacar y regresar repuestos de la bodega principal;
  - marcar lista;
  - cancelar, que devuelve lo sacado.

  (Reglas 2 a 7)
  - Los servicios están en `apps/workshop/work_orders.py`.
  - Permisos: recepción (`workshop.receive`) puede todo; el mecánico, solo en las órdenes que tiene asignadas, y sin precios.
  - Recibir y aprobar:
    - al recibir se guarda una lectura de kilometraje solo si cambió, y para bajarlo pide nota, como en la ficha de la moto;
    - aprobar marca lo pendiente y guarda el total aprobado hasta ese momento;
    - no se aprueba mano de obra sin precio.
  - Repuestos:
    - salen de la bodega principal con la referencia "Orden OT-…" y vuelven al costo con que salieron;
    - se puede quitar lo que no ha salido, aunque esté aprobado (el cliente aprobó y al final no se usó);
    - lo que salió solo se regresa.
  - "Lista" pide que no quede nada por aprobar y que todo repuesto aprobado esté puesto en la moto.
  - Cancelar devuelve lo que salió y no ha vuelto.
  - 19 tests y 52 fallos a propósito:
    - dos condiciones eran equivalentes y se quitaron: un usuario inactivo ya no tiene permisos, y un producto pendiente de precio siempre está inactivo;
    - cuatro sobrevivían por falta de test y destaparon que no se probaba que una orden cancelada con cambios pendientes siguiera cancelada, ni que una lista conservara sus repuestos; se agregaron esos tests.
- [x] **T3** Cobro y entrega:
  - mandar a la caja crea el pedido del día con los precios aprobados;
  - la caja lo cobra usando los movimientos ya hechos, sin revisión por precio;
  - entregar solo cobrada;
  - anular la venta de una orden la deja Lista, sin mover el inventario.

  (Reglas 8 a 10)
  - Servicios nuevos en `apps/workshop/work_orders.py`: `send_to_till`, `deliver`, `paid_sale` y `till_order`.
  - Mandar a la caja:
    - crea el pedido del día a nombre de recepción, con lo aprobado y no regresado a sus precios;
    - el pedido (`Order.work_order`) y cada línea (`OrderLine.work_order_line`) saben de qué orden salen;
    - no se manda dos veces mientras haya uno de hoy en la caja; si la caja lo cancela o se vence, se manda otra vez.
  - Cobro:
    - se cobra completo, sin revisión por precio (el de la mano de obra no es el del catálogo);
    - el documento electrónico va a nombre del cliente de la orden, salvo que la caja diga otro;
    - los repuestos no salen otra vez: la línea de venta apunta a la salida de la orden, que conserva su referencia "Orden OT-…", y el margen usa su costo.
  - `SaleLine.movement` pasó de uno a uno a llave foránea: si la venta se anula y la orden se cobra otra vez, la venta nueva usa la misma salida.
  - Anular la venta no mueve los repuestos de la orden y deja en su historia "Se anuló la venta …". Una devolución los regresa a la bodega de donde salieron (antes iba a la de la caja; para una venta normal es la misma).
  - Entregar exige la venta cobrada y no anulada, y guarda el kilometraje de salida (lectura nueva solo si cambió).
  - Cancelar saca el pedido de la caja; una orden cobrada no se cancela sin anular antes la venta.
  - 17 tests y 32 fallos a propósito; dos sobrevivían por falta de test (entregar con el mismo kilometraje no crea lectura y la nota se guarda) y se agregaron.
- [x] **T4** API `/api/workshop/orders/`:
  - lista por estado y mecánico (el mecánico solo ve las suyas);
  - ficha y cada acción de la T2 y la T3, con sus permisos;
  - 404 con el módulo apagado;
  - las órdenes en la ficha de la moto.

  (Reglas 6, 7, 11 y 12)
  - Está en `apps/workshop/order_api.py`:
    - `GET/POST orders/`: lista (por defecto las abiertas; `?status=`, `ALL`, `?mechanic=`, `?motorcycle=`) y recibir;
    - `GET orders/mechanics/`: los mecánicos activos para asignar;
    - `GET orders/<id>/`: la ficha con líneas, total aprobado y por aprobar, aprobaciones, historia, pedido en caja y venta;
    - `POST orders/<id>/<acción>/`: assign, diagnose, send-for-approval, approve, ready, send-to-till, deliver y cancel;
    - `POST orders/<id>/lines/`, `PATCH`/`DELETE orders/<id>/lines/<línea>/` y `POST .../take/` o `.../return/`.
  - Permisos:
    - entra quien tenga `workshop.receive` o `workshop.repair`;
    - el mecánico solo ve sus órdenes, y las demás le dan 404;
    - lo demás lo deciden los servicios: sus reglas dan 400 y sus permisos 403 con el mismo mensaje.
  - La ficha de la moto trae `work_orders`.
  - 15 tests y 24 fallos a propósito:
    - uno sobrevivía porque sin kilometraje también saltaba la regla de bajarlo, y ahora el test pide el mensaje exacto;
    - un corte por tiempo dejó un archivo mutado, se notó por el test que falló y se restauró.
- [x] **T5** Frontend, recepción. Pantalla "Órdenes":
  - recibir desde la ficha de la moto o buscándola;
  - lista por estado;
  - ficha con presupuesto, aprobación, hoja para imprimir, mandar a la caja, entregar y cancelar.

  (Reglas 1 a 4, 7 a 9)
  - Pantalla `pages/WorkOrders.tsx` (pestaña "Órdenes", con `workshop.receive` y el módulo activo; recepción abre en ella):
    - lista por estado (por defecto las abiertas) y búsqueda por número, placa o cliente entre las que trae;
    - "Recibir moto" busca la moto como en Motos; si no está, se registra allá primero;
    - la ficha asigna el mecánico, arma el presupuesto (repuestos al precio del catálogo, mano de obra con el precio de recepción), registra la aprobación, imprime, manda a la caja, entrega y cancela.
  - La ficha de la moto lista sus órdenes y la recibe en el taller si no tiene una abierta (`components/ReceiveOrder.tsx`, compartido).
  - La hoja (`components/WorkOrderPrint.tsx`) usa el formato de la de cotizaciones, con lo aprobado y lo por aprobar en tablas aparte y una línea para la firma.
  - Qué botones ve recepción según el estado lo decide `workOrder.ts`; el servidor vuelve a comprobarlo todo.
  - Sacar y regresar repuestos, el diagnóstico y "Lista" quedan para la pantalla del mecánico (T6).
  - 25 tests nuevos y 36 fallos a propósito.
- [ ] **T6** Frontend, mecánico. "Mis órdenes":
  - diagnóstico;
  - agregar repuestos y mano de obra;
  - sacar y regresar repuestos;
  - marcar lista.

  (Reglas 5 y 6)
- [ ] **T7** `seed_demo --taller`: un mecánico y órdenes en todos los estados, una con un cambio sin aprobar y una cancelada con su repuesto devuelto. (Regla 13)
- [ ] **T8** Prueba en el navegador y cierre:
  - el recorrido de los criterios de aceptación con la demo de taller;
  - la ferretería sin módulo de taller;
  - `docs/arquitectura.md`, `MEMORY.md` y la spec.
