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
- [ ] **T2** Servicios:
  - recibir (actualiza el kilometraje de la moto);
  - asignar mecánico;
  - diagnosticar;
  - agregar y quitar líneas: el mecánico sin precio, recepción con precio de mano de obra;
  - registrar la aprobación: lo agregado después queda por aprobar;
  - sacar y regresar repuestos de la bodega principal;
  - marcar lista;
  - cancelar, que devuelve lo sacado.

  (Reglas 2 a 7)
- [ ] **T3** Cobro y entrega:
  - mandar a la caja crea el pedido del día con los precios aprobados;
  - la caja lo cobra usando los movimientos ya hechos, sin revisión por precio;
  - entregar solo cobrada;
  - anular la venta de una orden la deja Lista, sin mover el inventario.

  (Reglas 8 a 10)
- [ ] **T4** API `/api/workshop/orders/`:
  - lista por estado y mecánico (el mecánico solo ve las suyas);
  - ficha y cada acción de la T2 y la T3, con sus permisos;
  - 404 con el módulo apagado;
  - las órdenes en la ficha de la moto.

  (Reglas 6, 7, 11 y 12)
- [ ] **T5** Frontend, recepción. Pantalla "Órdenes":
  - recibir desde la ficha de la moto o buscándola;
  - lista por estado;
  - ficha con presupuesto, aprobación, hoja para imprimir, mandar a la caja, entregar y cancelar.

  (Reglas 1 a 4, 7 a 9)
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
