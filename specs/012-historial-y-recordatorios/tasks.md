# Tareas — Spec 012

> Spec aprobada (PR #90, 2026-10-29). Decisiones en spec.md.

- [x] **T1** Backend, modelo:
  - `MaintenancePlan`: nombre, cada cuántos km y cuántos días (al menos uno, positivos), productos que lo cumplen y si está activo;
  - `MaintenanceReminder`: moto, plan, la orden que lo creó y la que lo cumplió, fecha y km de vencimiento, estado (pendiente, avisado, hecho, descartado) y nota;
  - un solo recordatorio abierto (pendiente o avisado) por moto y plan;
  - `MaintenanceNotice`: quién avisó, cuándo y cómo (WhatsApp o llamada).
  - Admin solo de lectura para recordatorios y avisos.

  (Reglas 2, 3 y 6)
  - Migración `workshop/0003_maintenance`. La base de datos también exige las reglas:
    - un plan tiene km, días o los dos, y mayores que cero;
    - el nombre del plan no se repite;
    - el recordatorio vence por fecha o por km;
    - uno solo abierto por moto y plan;
    - el hecho lleva la orden que lo cumplió;
    - el cerrado lleva la fecha de cierre.
  - Los planes sí se editan en el admin (son configuración), pero no se borran: se desactivan.
  - 9 tests y 17 fallos a propósito. Las restricciones se mutaron en la migración, porque los tests crean la base con ella.
    - Uno sobrevivía porque el test chocaba con la misma orden; ahora prueba con una visita posterior.
- [x] **T2** Backend, servicios (`workshop/maintenance.py`):
  - al entregar una orden, cerrar el recordatorio anterior y crear el siguiente por cada plan que cumple;
  - uso diario estimado con las lecturas y fecha estimada por km (funciones puras);
  - qué vence (ventana de 7 días, vencidos primero, vence ya si una lectura pasó los km);
  - avisar, ajustar y descartar, con sus permisos y su historia.

  (Reglas 3 a 6 y 9)
  - `work_orders.deliver` llama a `maintenance.on_delivered`. Cuenta lo cobrado: lo aprobado y no regresado, también la mano de obra si está en un plan.
  - Si la orden se entrega otra vez después de anular su venta (spec 011), recalcula el mismo recordatorio en vez de cerrarlo y crear otro.
  - Un plan inactivo cierra como hecho lo que tenía abierto, pero no crea el siguiente.
  - Funciones puras:
    - `daily_usage`: los últimos 12 meses y al menos 14 días entre la primera y la última lectura. Si el km bajó (tablero nuevo), cuenta desde esa lectura;
    - `km_due_date`: redondea los días hacia arriba; si una lectura ya pasó los km, vence ese día.
  - `due_of` dice cuándo vence, si es por km y si el km es estimado ("aprox."). `due_reminders` da la lista: 7 días de ventana, vencidos primero, filtro por plan y avisados a pedido.
  - 17 tests y 34 fallos a propósito. Todos mueren.
- [x] **T3** API:
  - planes (`catalog.edit`);
  - lista de mantenimientos con filtros, y las acciones avisar, ajustar y descartar (`workshop.receive`);
  - historial en la ficha de la moto: órdenes con lo que se les hizo y sus recordatorios.
  - Todo con 404 si el módulo está apagado.

  (Reglas 1, 7 a 10)
  - Rutas en `apps/workshop/maintenance_api.py`:
    - `GET/POST plans/` y `GET/PATCH plans/<id>/`. Los ve recepción, pero solo los crea o cambia quien tiene `catalog.edit`. No se borran. Piden al menos un producto, un intervalo mayor que cero y un nombre que no se repita;
    - `GET maintenance/`: lo que vence, los vencidos primero. Admite `?plan=` y, con `?notified=1`, también los avisados;
    - `POST maintenance/<id>/notify|adjust|dismiss/` devuelve la fila.
    - Cada fila trae la moto, el dueño actual con su teléfono, el plan, cuándo vence, si es por km aprox., el uso diario y los avisos.
  - `history.py` arma el historial y los recordatorios de la ficha de la moto (`history` y `reminders`):
    - lo hecho y el total solo en las entregadas, sin lo regresado;
    - la fecha de entrega sale de su historia;
    - los recordatorios abiertos van primero.
  - 18 tests y 28 fallos a propósito. Tres sobrevivían porque DRF ya recorta, rechaza vacío y valida que el nombre no se repita: ese código se quitó. Dos por tests flojos (una orden abierta con algo aprobado, un recordatorio hecho), que se reforzaron.
- [x] **T4** Frontend, pantalla "Mantenimientos":
  - lista que vence, con el botón de WhatsApp (`wa.me` con el 57 y el mensaje), marcar avisado, ajustar y descartar;
  - pestaña "Planes" para quien maneja el catálogo.

  (Reglas 2, 7 a 9)
  - Pantalla `pages/Maintenance.tsx`, en el menú después de Productos para que el jefe de bodega siga abriendo en sus pantallas:
    - "Por vencer", con `workshop.receive`: la lista, el filtro por plan y los avisados a pedido. La ficha trae:
      - el enlace a WhatsApp (`wa.me`, que se abre en otra pestaña);
      - "Avisado por WhatsApp" y "Avisado por llamada";
      - ajustar y descartar, con nota.
    - "Planes", con `catalog.edit`: crear y cambiar planes con el buscador de productos.
  - `maintenance.ts` arma:
    - el número de WhatsApp (celular de Colombia con el 57; un fijo no tiene botón);
    - el mensaje, con el nombre comercial del negocio;
    - el texto de cuándo vence ("Venció hace 3 días", "Vence en 2 días por km (aprox.)");
    - la validación del plan.
  - La pestaña inicial se decide en cada render: la sesión puede cargar después de la pantalla.
  - 20 tests nuevos y 37 fallos a propósito. Todos mueren.
- [x] **T5** Frontend, historial en la ficha de la moto, con sus recordatorios. La ficha de una orden entregada muestra el próximo mantenimiento que se le calculó. (Reglas 1 y 3)
  - La ficha de la moto (`Motorcycles.tsx`) tiene dos secciones:
    - **Historial**: cada orden entregada con fecha, km de salida, mecánico, lo que pidió, el diagnóstico, lo que se le hizo y el total; las demás, con su estado;
    - **Mantenimientos**: sus recordatorios con la fecha y/o los km, el estado, cuándo vence (solo los abiertos), con qué orden se hizo y su nota.
  - La ficha de la orden (`WorkOrders.tsx`) muestra "Próximo mantenimiento" con los recordatorios que creó; la API agrega `next_maintenance`.
  - `components/ReminderList.tsx` se usa en las dos fichas, y `maintenance.reminderTarget` arma el texto de la fecha y los km.
  - 6 tests nuevos (1 del backend) y 18 fallos a propósito. Todos mueren.
- [x] **T6** `seed_demo --taller`: planes de ejemplo y un recordatorio en cada estado, uno de ellos vencido por km estimados. (Regla 11)
  - Tres planes: cambio de aceite (3.000 km o 90 días), revisión de frenos (5.000 km o 180 días) y kit de arrastre (15.000 km).
  - Cuatro motos pasaron por el taller meses atrás, en una de sus lecturas (`_past_visit`): la orden se recibe, se arregla, se cobra y se entrega con los mismos servicios, y después se le corren las fechas. Se cobran en el turno de hoy para no tocar los cierres de días pasados.
  - Quedan: el aceite de la Suzuki, vencido por fecha; el de la Pulsar, que vence por km estimados (unos 50 km al día); el de la Boxer, avisado por WhatsApp; el de la Honda, hecho con la orden de hoy, que crea el siguiente; y su kit, descartado.
  - La ferretería sigue sin planes. 3 tests nuevos y 14 fallos a propósito, todos detectados.
- [x] **T7** Prueba en el navegador y cierre:
  - el recorrido de los criterios de aceptación con la demo de taller;
  - la ferretería sin módulo de taller;
  - `docs/arquitectura.md`, `MEMORY.md` y la spec.

  38 de 38 comprobaciones bien, con Chrome sin ventana sobre la demo del taller y la ferretería. No apareció ningún fallo de la app.
  - **Plan**: el admin crea "Lubricación de cadena" (1.000 km o 30 días, con la grasa). Con 0 km y 0 días no deja guardar, ni la pantalla ni la API. Se usó otro plan porque el de aceite ya viene en la demo.
  - **Lista de Diana**:
    - los vencidos van primero, en rojo, y la Pulsar vence "en 5 días por km (aprox.)", con unos 50 km al día;
    - el botón abre `https://wa.me/573001234567?text=…` con el cliente, la moto, el plan y el negocio;
    - al avisar, queda con quién y cuándo, y sigue en la lista como avisado;
    - con un teléfono fijo no hay botón;
    - el ajuste a diciembre y el descarte con nota la sacan de la lista.
  - **Próximo mantenimiento**:
    - la Boxer se entrega con 15.420 km sin las bandas regresadas;
    - queda el aceite para 90 días y 18.420 km, y también los frenos, por las pastillas;
    - el aviso anterior se cierra como hecho con esa orden;
    - la Yamaha, cobrada solo con grasa, no crea el del aceite.
  - **Historial**: la ficha de la Boxer muestra la orden de hoy y la visita de hace 4 meses, cada una con lo cobrado, el mecánico y el total, sin las bandas. La Suzuki muestra su orden cancelada y el recordatorio descartado con su nota.
  - **Permisos**:
    - el mecánico no ve Mantenimientos (403 en la API);
    - la caja no lo ve ni crea planes (403);
    - en la ferretería no existe nada de esto (404).
  - **Pendiente menor, corregido (2026-10-30)**: en la lista, la insignia "Pendiente" quedaba pegada al borde de la tabla. La causa era que la moto, el dueño y el plan no se partían (`.sales-list`). Ahora se parten en esa tabla (`.maintenance-list`), y el estado y el teléfono quedan en una línea. Se midió a 1440 y 1024 px.
