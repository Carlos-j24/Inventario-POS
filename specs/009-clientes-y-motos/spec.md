# Spec 009 — Clientes y motos (módulo de taller, etapa 1)

> Estado: **borrador (2026-10-27)**, pendiente de aprobación. Tareas en tasks.md.

## Problema
Un taller de motos con venta de repuestos contrató el sistema (propuesta del 2026-10-25, alcance sin cambios). Hoy la app sabe de productos, ventas y clientes para la factura, pero no de **motos**: no hay dónde guardar la placa, la marca o el kilometraje, ni quién es el dueño. Sin eso no se pueden hacer las órdenes de trabajo (spec 010) ni el historial y los recordatorios de mantenimiento (spec 011).

La ferretería, en cambio, no debe ver nada de esto.

## Objetivo
Que recepción encuentre o registre en segundos a un cliente y su moto (por placa, chasis, cédula, nombre o teléfono), con el dueño actual y los anteriores, en un módulo de taller que cada instalación activa o deja apagado.

## Reglas
1. **Módulo de taller**: una casilla "Módulo de taller" en los datos del negocio (admin de Django), apagada por defecto. Apagado, la API del taller responde 404 y la app no muestra nada del taller. La app sabe si está activo al iniciar sesión (`/api/auth/me/`).
2. **Permiso nuevo** `workshop.receive` ("Recibir motos y llevar clientes y motos del taller") y **rol nuevo** "Recepción de taller" con ese permiso y `sales.create` (para cotizar en la spec 010). El rol Administrador lo recibe también.
3. **El cliente del taller es el mismo `Customer`** que ya usa la caja para la DIAN: una sola ficha por persona, con su documento obligatorio como hoy. Desde el taller, además, el **teléfono es obligatorio** (para avisar cuando la moto esté lista).
4. La búsqueda de clientes encuentra también por **teléfono** (hoy solo por documento o nombre).
5. **Moto**: placa, número de chasis (VIN), marca, modelo, año, cilindraje (cc), color, kilometraje con la fecha de la lectura, notas y activa/inactiva.
   - La placa se guarda en mayúsculas, sin espacios ni guiones, y **no se repite** entre motos.
   - Sin placa (moto nueva sin matricular), el **chasis es obligatorio**; el chasis tampoco se repite. La placa se agrega después.
   - Marca: texto libre con sugerencias de las marcas comunes en Colombia (AKT, Bajaj, Honda, Yamaha, Suzuki, TVS, Hero, Kawasaki, KTM, Victory…).
6. **Kilometraje**: solo sube. Para bajarlo (cambio de tablero o error de digitación) hace falta una nota que lo explique.
7. **Dueño**: cada moto tiene un dueño actual, y un cliente puede tener varias motos. **Cambiar de dueño** cierra el registro del anterior (con la fecha) y abre el del nuevo: el historial de dueños se conserva y lo que se le haga a la moto sigue con la moto.
8. **Pantalla "Motos"** (solo con el módulo activo y el permiso):
   - buscar por placa, chasis, cédula, nombre o teléfono del dueño;
   - ver la ficha de la moto con su dueño actual y los anteriores;
   - registrar una moto con un cliente existente o uno nuevo, en el mismo paso;
   - corregir los datos de la moto, actualizar el kilometraje y cambiar el dueño.
9. Las motos no se borran: se desactivan (más adelante tendrán órdenes e historial).
10. `seed_demo --taller` siembra una demo de taller de motos: módulo activo, catálogo de repuestos de moto, clientes y motos de ejemplo. Sin `--taller`, la demo de la ferretería queda igual.
11. Sin librerías nuevas.

## Decisiones (2026-10-27)
1. **Un solo sistema con módulo de taller**, no una copia aparte: ferretería y taller comparten caja, inventario, cotizaciones y reportes, y cada arreglo se hace una vez.
2. **El cliente del taller es el mismo de la caja, con documento obligatorio**: la moto, las compras y las facturas de una persona quedan juntas. _Descartada:_ documento opcional al recibir la moto (más rápido, pero deja fichas a medias para facturar).
3. **Placa única; sin placa, por chasis.** _Descartada:_ placa siempre obligatoria (no sirve para motos nuevas).
4. **Dueño actual más historial de dueños.** _Descartada:_ guardar solo el dueño actual.
5. **El módulo se activa con una casilla en los datos del negocio.** _Descartada:_ una variable del servidor (más segura contra errores, pero obliga a reinstalar para activarlo).

## Fuera de alcance (specs siguientes)
- Órdenes de trabajo: ingreso con fotos, diagnóstico, mecánico, repuestos, mano de obra y entrega (spec 010).
- Historial de trabajos por moto y recordatorios de mantenimiento (spec 011).
- Factura electrónica DIAN (spec 005, T7 y T8) y avisos por WhatsApp.

## Criterios de aceptación
- Con el módulo apagado, la ferretería no ve la pestaña "Motos" y `/api/workshop/…` responde 404.
- Recepción registra a "Don Jorge" (cédula y teléfono) con su Bajaj Boxer placa `xyz-12a`; queda guardada como `XYZ12A` y la encuentra después por placa, cédula, nombre o teléfono.
- Una segunda moto con placa `XYZ12A` se rechaza; una moto sin placa ni chasis también.
- Don Jorge vende su moto a otro cliente: la ficha muestra al nuevo dueño y a Don Jorge en el historial, con las fechas.
- El kilometraje no baja sin una nota.
- Un usuario sin `workshop.receive` no ve la pantalla ni puede usar la API.
- `seed_demo --taller` deja una demo de taller lista para mostrar.
