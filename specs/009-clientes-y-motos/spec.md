# Spec 009 — Clientes y motos (módulo de taller, etapa 1)

> Estado: **aprobada (2026-10-27)**. Decisiones tomadas en Carlos-j24/Inventario-POS#68 y en el repo privado del taller; ver la decisión 1. Tareas en tasks.md.

## Problema
El primer cliente es **Moto Repuestos y Lavadero Arias**, un taller de motos con venta de repuestos y lavadero (propuesta del 2026-10-25, alcance sin cambios más el cobro de lavados). Hoy la app sabe de productos, ventas y clientes para la factura, pero no de **motos**: no hay dónde guardar la placa, la marca o el kilometraje, ni quién es el dueño. Sin eso no se pueden hacer las órdenes de trabajo ni el historial y los recordatorios de mantenimiento.

La ferretería, en cambio, no debe ver nada de esto.

## Objetivo
Que recepción encuentre o registre en segundos a un cliente y su moto (por placa, chasis, cédula, nombre o teléfono), con el dueño actual y los anteriores, en un módulo de taller que cada instalación activa o deja apagado.

## Reglas
1. **Módulo de taller**: una casilla "Módulo de taller" en los datos del negocio (admin de Django), apagada por defecto. Apagado, la API del taller responde 404 y la app no muestra nada del taller. La app sabe si está activo al iniciar sesión (`/api/auth/me/`).
2. **Permiso nuevo** `workshop.receive` ("Recibir motos y llevar clientes y motos del taller") y **rol nuevo** "Recepción de taller" con ese permiso y `sales.create` (para cotizar trabajos). El rol Administrador lo recibe también.
3. **El cliente del taller es el mismo `Customer`** que ya usa la caja para la DIAN: una sola ficha por persona, con su documento obligatorio como hoy. Desde el taller, además, el **teléfono es obligatorio** (para avisar cuando la moto esté lista).
4. La búsqueda de clientes encuentra también por **teléfono** (hoy solo por documento o nombre).
5. **Moto**: placa, número de chasis (VIN), marca, modelo, año, cilindraje (cc), color, kilometraje con la fecha de la lectura, notas y activa/inactiva.
   - La placa se guarda en mayúsculas, sin espacios, guiones ni puntos, y **no se repite** entre motos.
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
10. `seed_demo --taller` siembra la demo del taller: módulo activo, datos del negocio de un taller, catálogo de repuestos de moto con su historia, y clientes y motos de ejemplo (una con dueño anterior y una sin placa). Sin `--taller`, la demo de la ferretería queda igual.
11. Sin librerías nuevas.

## Decisiones (2026-10-27)
1. **Un solo software con módulo de taller; una instalación por cliente.** Ferretería y taller comparten caja, inventario, cotizaciones y reportes, y cada arreglo se hace una vez. Cada cliente tiene su propia instalación (servidor o contenedor y base de datos); lo propio de Arias (logo, configuración, datos) vive en su repo privado de instalación. _Descartadas:_ un repo aparte por cliente (se probó el mismo día: cada arreglo habría que hacerlo dos veces) y la multiempresa real con una sola instalación para todos (semanas de trabajo y el riesgo de mezclar datos entre empresas; se retoma con unos 8–10 clientes en mensualidad).
2. **El cliente del taller es el mismo de la caja, con documento obligatorio**: la moto, las compras y las facturas de una persona quedan juntas. _Descartada:_ documento opcional al recibir la moto (más rápido, pero deja fichas a medias para facturar).
3. **Placa única; sin placa, por chasis.** _Descartada:_ placa siempre obligatoria (no sirve para motos nuevas).
4. **Dueño actual más historial de dueños.** _Descartada:_ guardar solo el dueño actual.
5. **El módulo se activa con una casilla en los datos del negocio.** _Descartada:_ una variable del servidor (más segura contra errores, pero obliga a reinstalar para activarlo).

## Fuera de alcance (specs siguientes)
- **Spec 010, lavados**: cobrar lavados en la caja como servicios, sin inventario. El mismo tipo de producto servirá para la mano de obra.
- **Spec 011, órdenes de trabajo**: ingreso con fotos, diagnóstico, mecánico, repuestos, mano de obra y entrega.
- **Spec 012**: historial de trabajos por moto y recordatorios de mantenimiento.
- Factura electrónica DIAN (spec 005, T7 y T8), avisos por WhatsApp y el nombre y logo de cada negocio en la app.

## Criterios de aceptación
- Con el módulo apagado, la ferretería no ve la pestaña "Motos" y `/api/workshop/…` responde 404.
- Recepción registra a "Don Jorge" (cédula y teléfono) con su Bajaj Boxer placa `xyz-12a`; queda guardada como `XYZ12A` y la encuentra después por placa, cédula, nombre o teléfono.
- Una segunda moto con placa `XYZ12A` se rechaza; una moto sin placa ni chasis también.
- Don Jorge vende su moto a otro cliente: la ficha muestra al nuevo dueño y a Don Jorge en el historial, con las fechas.
- El kilometraje no baja sin una nota.
- Un usuario sin `workshop.receive` no ve la pantalla ni puede usar la API.
- `seed_demo --taller` deja una demo de taller lista para mostrar.
