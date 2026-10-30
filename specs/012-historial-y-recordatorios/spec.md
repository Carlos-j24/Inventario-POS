# Spec 012 — Historial y recordatorios de mantenimiento (módulo de taller, etapa 4)

> Estado: **aprobada (2026-10-29)** en el PR #90. Decisiones tomadas con Carlos el 2026-10-29. Tareas en tasks.md.

## Problema
Con la spec 011, cada moto ya entra al taller con una orden de trabajo. Pero todavía faltan dos cosas:
- **Historial**: no hay dónde ver de un vistazo todo lo que se le ha hecho a una moto. Las órdenes están, pero sueltas.
- **Recordatorios**: nadie le avisa al cliente cuándo le toca el próximo mantenimiento. Ese aviso es el que hace volver al cliente.

La propuesta (2026-10-25) incluye "todo lo que se le ha hecho a cada moto y aviso del próximo mantenimiento por fecha o kilometraje". Son unas 30 horas. Deja por fuera los avisos automáticos por WhatsApp.

## Objetivo
1. La ficha de cada moto muestra su historial: qué se le hizo, cuándo, con cuántos km y quién.
2. Al entregar una moto, el sistema calcula solo cuándo le toca el próximo mantenimiento.
3. Recepción tiene una lista de los mantenimientos que vencen. Desde ahí avisa al cliente por WhatsApp con un clic y deja registrado que avisó.

## Reglas
1. **Historial de la moto**, en su ficha (spec 009). Muestra sus órdenes entregadas, de la más reciente a la más antigua, cada una con:
   - la fecha de entrega y el kilometraje;
   - lo que pidió el cliente y el diagnóstico;
   - lo que se le hizo: los repuestos y la mano de obra que se cobraron, sin lo regresado;
   - el mecánico y el total.

   También muestra las órdenes abiertas y las canceladas, cada una con su estado.
2. **Planes de mantenimiento**: los define quien maneja el catálogo (`catalog.edit`). Cada plan tiene:
   - un nombre, por ejemplo "Cambio de aceite";
   - cada cuántos kilómetros, cada cuántos días, o las dos cosas (al menos una);
   - los productos o servicios que lo cumplen, por ejemplo los aceites;
   - si está activo.

   Un plan inactivo no genera recordatorios nuevos. Los que ya tiene siguen hasta cerrarse.
3. **Próximo mantenimiento**: al **entregar** una orden (spec 011) que se cobró con alguno de los productos de un plan, se crea un recordatorio para esa moto y ese plan:
   - para la fecha de entrega más los días del plan;
   - y para el kilometraje de salida más los km del plan.

   El recordatorio anterior de esa moto y ese plan se cierra como **hecho**, con la orden que lo cumplió.
4. **Kilometraje estimado**: entre visitas se estima cuántos km lleva la moto.
   - El cálculo usa las lecturas de kilometraje (spec 009) de los últimos 12 meses: km recorridos sobre días pasados, entre la primera y la última.
   - Hacen falta al menos dos lecturas separadas por 14 días o más. Una lectura con nota de cambio de tablero corta la cuenta: solo valen las lecturas que vienen después.
   - Con el uso diario se calcula la fecha en que la moto llegaría a los km del recordatorio. La pantalla la muestra como "aprox.".
   - Sin lecturas suficientes, el recordatorio solo vence por fecha, o por kilometraje cuando la moto vuelva y se lea.
5. **Cuándo vence**: un recordatorio vence en la primera de dos fechas: la del plan o la estimada por kilometraje.
   - Aparece en la lista desde **7 días antes** de vencer.
   - Si la moto vuelve y su kilometraje ya pasó el del recordatorio, vence ya.
6. **Estados del recordatorio**:
   - **Pendiente** → **Avisado** → **Hecho**;
   - también **Descartado**, por ejemplo si la moto se vendió o el cliente no quiere el aviso. Se descarta con una nota.

   Avisar no lo cierra: sigue en la lista, marcado como avisado, hasta que se haga o se descarte. Cada aviso queda con quién y cuándo, y se puede avisar otra vez.
7. **Lista "Mantenimientos"** para recepción (`workshop.receive`): los recordatorios que vencen, los vencidos primero.
   - Cada uno muestra la moto, el dueño actual y su teléfono, el plan, por qué vence (fecha o km aprox.) y si ya se avisó.
   - Se puede filtrar por plan y ver también los avisados.
8. **Avisar por WhatsApp**: un botón abre WhatsApp (enlace `wa.me`) con el número del dueño y un mensaje ya escrito con el nombre del cliente, la moto, el plan y el nombre del negocio.
   - Lo envía recepción desde su WhatsApp; el sistema no manda nada solo.
   - Después se marca "avisado". También se puede marcar avisado sin el botón, por ejemplo si avisó por llamada.
   - Los números de Colombia se escriben con el 57 delante; si el teléfono no es un celular válido, el botón no aparece.
9. **Ajustar**: recepción puede cambiar la fecha o el kilometraje de un recordatorio pendiente o avisado, con una nota, por ejemplo "el cliente dijo que viene en diciembre".
10. **Sin módulo de taller** (spec 009), nada de esto aparece y la API responde 404.
11. `seed_demo --taller` siembra:
    - planes de ejemplo;
    - recordatorios: uno vencido por fecha, uno que vence por km estimados, uno avisado, uno hecho y uno descartado.

    La ferretería queda igual.
12. Sin librerías nuevas.

## Decisiones (2026-10-29)
1. **Planes automáticos**: el próximo mantenimiento sale de planes con sus productos, y recepción lo ajusta si hace falta. Así no depende de que alguien se acuerde de llenarlo en cada entrega.
   - _Descartado:_ que recepción escriba la fecha a mano al entregar (más simple, pero se olvida).
2. **Lista y WhatsApp a mano**: recepción avisa desde la lista con un enlace `wa.me` y marca "avisado". No hay costos de terceros ni plantillas aprobadas por Meta, y la propuesta excluye los avisos automáticos.
   - _Descartado por ahora:_ envío automático por la API de WhatsApp Business. Se cotiza aparte si Arias lo pide.
3. **Kilometraje estimado con el uso**: entre visitas se estima con las lecturas, y se muestra como aproximado.
   - _Descartado:_ que entre visitas solo cuente la fecha (para una moto de mensajería, el aviso por km llegaría tarde).

## Fuera de alcance
- Avisos automáticos por WhatsApp, SMS o correo (decisión 2).
- Calcular recordatorios con las órdenes anteriores a crear un plan. Al empezar con Arias no hay historial; si hace falta, se agrega después.
- Recordatorios por lavados: los lavados no se ligan a una moto (spec 010).
- Hoja impresa del historial.
- Comisiones de los mecánicos y ventas a crédito (como en la spec 011).

## Criterios de aceptación
- **Historial**: la ficha de la Boxer `XYZ12A` muestra la orden entregada con su fecha, sus km, el aceite, las pastillas, la mano de obra, el mecánico y el total. No muestra las bandas que se regresaron. Las órdenes abiertas y canceladas aparecen con su estado.
- **Plan**: el admin crea "Cambio de aceite: cada 3.000 km o 90 días", con los dos aceites. "Cada 0 km y 0 días" no se puede guardar.
- **Próximo mantenimiento**:
  - Diana entrega la Boxer con 15.420 km y su orden llevaba aceite; queda un recordatorio para 90 días después y 18.420 km;
  - una entrega sin aceite no crea recordatorio de aceite;
  - la siguiente entrega con aceite cierra el anterior como hecho y crea uno nuevo.
- **Estimación**: una moto que anda 50 km al día y está a 1.000 km del recordatorio aparece como "aprox." en unos 20 días, y entra a la lista 7 días antes.
- **Aviso**:
  - Diana abre la lista y ve los vencidos primero;
  - el botón de WhatsApp abre `https://wa.me/573001234567?text=…` con el mensaje;
  - al marcarlo avisado, queda con quién y cuándo, y sigue en la lista como avisado;
  - un teléfono fijo no muestra el botón.
- **Ajustar y descartar**: Diana corre un recordatorio a diciembre con una nota. Descarta el de una moto vendida, con una nota, y sale de la lista.
- **Permisos**: el mecánico no ve la lista; la caja no crea planes. Sin el módulo de taller, nada de esto aparece.
