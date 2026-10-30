# Tareas — Spec 012

> Spec en borrador (2026-10-29), para aprobar. Decisiones en spec.md.

- [ ] **T1** Backend, modelo:
  - `MaintenancePlan`: nombre, cada cuántos km y cuántos días (al menos uno, positivos), productos que lo cumplen y si está activo;
  - `MaintenanceReminder`: moto, plan, la orden que lo creó y la que lo cumplió, fecha y km de vencimiento, estado (pendiente, avisado, hecho, descartado) y nota;
  - un solo recordatorio abierto (pendiente o avisado) por moto y plan;
  - `MaintenanceNotice`: quién avisó, cuándo y cómo (WhatsApp o llamada).
  - Admin solo de lectura para recordatorios y avisos.

  (Reglas 2, 3 y 6)
- [ ] **T2** Backend, servicios (`workshop/maintenance.py`):
  - al entregar una orden, cerrar el recordatorio anterior y crear el siguiente por cada plan que cumple;
  - uso diario estimado con las lecturas y fecha estimada por km (funciones puras);
  - qué vence (ventana de 7 días, vencidos primero, vence ya si una lectura pasó los km);
  - avisar, ajustar y descartar, con sus permisos y su historia.

  (Reglas 3 a 6 y 9)
- [ ] **T3** API:
  - planes (`catalog.edit`);
  - lista de mantenimientos con filtros, y las acciones avisar, ajustar y descartar (`workshop.receive`);
  - historial en la ficha de la moto: órdenes con lo que se les hizo y sus recordatorios.
  - Todo con 404 si el módulo está apagado.

  (Reglas 1, 7 a 10)
- [ ] **T4** Frontend, pantalla "Mantenimientos":
  - lista que vence, con el botón de WhatsApp (`wa.me` con el 57 y el mensaje), marcar avisado, ajustar y descartar;
  - pestaña "Planes" para quien maneja el catálogo.

  (Reglas 2, 7 a 9)
- [ ] **T5** Frontend, historial en la ficha de la moto, con sus recordatorios. La ficha de una orden entregada muestra el próximo mantenimiento que se le calculó. (Reglas 1 y 3)
- [ ] **T6** `seed_demo --taller`: planes de ejemplo y un recordatorio en cada estado, uno de ellos vencido por km estimados. (Regla 11)
- [ ] **T7** Prueba en el navegador y cierre:
  - el recorrido de los criterios de aceptación con la demo de taller;
  - la ferretería sin módulo de taller;
  - `docs/arquitectura.md`, `MEMORY.md` y la spec.
