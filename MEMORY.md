# MEMORY.md — Inventario-POS
Memoria del proyecto entre sesiones. Máximo ~50 líneas: resume o elimina lo que ya no aporte.

## Estado actual (2026-10-27)
- **Spec 001 (MVP)** completa: backend (roles, catálogo, kardex, ventas con IVA incluido, caja con pago mixto y arqueo, devoluciones, sesión en cookie), frontend React con modo sin conexión e instalable, y despliegue Docker + PostgreSQL.
- **Specs 002 y 003** completas: pedidos vendedor → caja (código de 4 dígitos; la venta guarda quién vendió y quién cobró) y pantallas de supervisor y administrador (ventas, usuarios, roles, contraseña temporal obligatoria).
- **Spec 004 (reportes)** completa: costo promedio ponderado guardado en cada salida, pantalla Reportes (ventas, productos, arqueos; inventario valorizado y márgenes con `reports.costs`) y CSV para Excel.
- **Spec 006 (catálogo e inventario en la app)** completa (2026-10-19): pantallas Productos (historial de precios; sin `catalog.edit_prices` el producto queda pendiente de precio), Ajustes (los aprueba `inventory.adjust`), Conteos ciegos (esperado a la hora de cada línea) y Traslados en un paso (`inventory.transfer`); ventas sin conexión de productos desactivados o con fecha anterior a un conteo aprobado quedan con `needs_review`.
- **Spec 007 (cotizaciones)** completa (2026-10-22): cotizar con vigencia (8 días), imprimir en hoja carta o PDF, convertir en pedidos por partes cobrados al precio cotizado (sin revisión) y reporte de conversión por vendedor. **Spec 008** (bodega por defecto) completa el mismo día: bodega principal en el admin y la última elegida por usuario en cada equipo.
- **Spec 011 (órdenes de trabajo)** aprobada (PR #81) y en curso: T1 a T7 hechas (modelo, movimientos de taller, rol Mecánico, servicios en `workshop/work_orders.py`, cobro por un pedido de caja que reutiliza las salidas de la orden, API en `workshop/order_api.py` pantalla "Órdenes" de recepción en `pages/WorkOrders.tsx` y "Mis órdenes" del mecánico en `pages/MyOrders.tsx`).
- **Spec 010 (servicios: lavados)** completa (2026-10-28): `Product.is_service` se cobra, anula y devuelve sin mover inventario, no entra a Entradas, Ajustes, Traslados ni Conteos, y en Márgenes va aparte de la mercancía. Servirá también para la mano de obra (011).
- **Spec 009 (clientes y motos)** completa (2026-10-27): módulo de taller (`Business.workshop_enabled`), motos con placa o chasis, dueño actual e historial, kilometraje que solo baja con nota y pantalla Motos para Recepción de taller.
- **Primer cliente (2026-10-27): Moto Repuestos y Lavadero Arias**, taller de motos con repuestos y lavadero. Módulo de taller: spec 009 (clientes y motos) completa, lavados (010) completa, órdenes de trabajo (011) en curso, luego historial y recordatorios (012) y DIAN (005 T7/T8). Su instalación (logo, configuración) va en el repo privado Carlos-j24/taller-arias. Forma de pago aún por definir.
- Datos de demostración en el repo: `manage.py seed_demo` (app `apps/demo`), dos semanas de historia con semilla fija para mostrar la app; `--taller` siembra un taller de motos (perfil en `apps/demo/workshop.py`).
- Repositorio público Carlos-j24/Inventario-POS. main exige 5 checks: pytest 3.12 y 3.14, pytest-postgres, frontend y docker (`scripts/smoke-test.sh`).

## Decisiones (y por qué)
- AGENTS.md es la fuente única de reglas; CLAUDE.md solo lo importa → mismas reglas para Claude Code y OpenCode.
- Pensada para ferretería → unidades con conversión (rollo/metro) y venta fraccionada desde el MVP. Lotes y vencimientos quedan para cuando llegue una droguería.
- Un solo software con módulos que cada instalación activa, y una instalación por cliente (2026-10-27) → cada arreglo se hace una vez y los datos de un cliente nunca tocan los de otro. Se probó un repo aparte para el taller y se deshizo el mismo día. Multiempresa real: con unos 8–10 clientes en mensualidad. El logo también es de cada instalación (`BRAND_DIR`, 2026-10-29), nunca en este repo público.
- Stock como libro de movimientos + saldo cacheado y bloqueado (`select_for_update`) → kardex auditable y sin carreras entre cajas.
- Modo sin conexión: el POS genera UUID por documento y se sincroniza con reintentos idempotentes; puede dejar stock negativo (`needs_review`) antes que bloquear una venta.
- Roles editables y permisos fijos por código → el admin crea roles nuevos sin tocar el código.
- Precios con IVA incluido → así se exhiben en ferretería; el POS suma totales y el backend separa la base y el IVA.
- Turno por caja física, no por cajero (decisión del equipo, 2026-10-16) → el arqueo cuadra el cajón; si cambia el cajero, se cierra y se abre otro turno.
- Sesión en cookie y no JWT → sin dependencias nuevas y la cookie HttpOnly no la lee JavaScript; obliga a servir la PWA y la API desde el mismo dominio.
- gunicorn + WhiteNoise en un solo contenedor (decisión del equipo, 2026-10-16) → más simple que nginx aparte; HTTPS lo pone un proxy delante (Caddy).
- Pago mixto permitido (decisión del equipo) → tarjeta y transferencia no pueden pasarse del total; el efectivo da vueltas.

## Aprendizajes y errores a evitar
- Lo impreso se comprueba imprimiendo a PDF con Chrome sin ventana (`chrome --headless=new --print-to-pdf`) y leyendo el PDF: los tests no ven la página impresa (en la T5 de la spec 007 salía angosta y con hojas en blanco).
- Pasar el foco tras escanear con `setTimeout` deja colar la tecla siguiente (lo destapó la prueba en el navegador de la T6 de la spec 006): usar `flushSync` y enfocar en el acto.
- El admin de Django valida las restricciones de la base de datos antes de `save()`: una regla que `save()` arregla (marcar otra bodega principal) hay que sacarla de `validate_constraints` (spec 008 T3).
- Un test de redondeo con precios "redondos" (3.200) no prueba nada: el centavo perdido solo aparece con precios con centavos (3.199,99).
- El servidor de Vite (5173) es otro origen para Django: sin `CSRF_TRUSTED_ORIGINS` el login falla con 403 "Origin checking failed". Solo pasa en desarrollo.
- Vitest sin `globals`: Testing Library no limpia el DOM entre tests; hace falta `afterEach(cleanup)` en `test-setup.ts`.
- El panel del navegador de Claude (Electron) no registra service workers ("unknown error when fetching the script"): el SW se prueba en Chrome (con Claude in Chrome funciona).
- Chrome lanza "beforeinstallprompt" una sola vez por carga y nunca si la app ya está instalada: el botón "Instalar app" desaparece entonces (no es un fallo).
- `navigator.onLine` solo dice si hay red local: el estado "En línea" sale de `/api/health/` (fallo encontrado en Chrome con el servidor apagado).
- En el service worker: nunca guardar respuestas con error como copia sin red, y borrar los `/assets` viejos en cada versión nueva (si no, la caché crece sin límite).
- En Windows, un `fetch` a un puerto local apagado tarda unos 8 s en fallar: por eso `api.ts` tiene un límite de 10 s y lo trata como sin conexión.
- El inicio de sesión admite 5 intentos por minuto (`LOGIN_RATE`): una prueba que cambia de usuario varias veces seguidas recibe 429.
- `gh pr merge --auto` sin checks obligatorios fusiona AL INSTANTE (pasó con el PR #8). Ahora main exige los checks, pero GitHub a veces no dispara la fusión al quedar todo en verde (PR #9, #10, #27): revisar y fusionar a mano.
- Los tests de concurrencia (dos cajas a la vez) no corren en SQLite: el job `pytest-postgres` del CI corre la suite contra PostgreSQL. Llevan `django_db(transaction=True, serialized_rollback=True)`: sin lo segundo vacían la base, incluidos los datos de las migraciones (unidades, roles), y rompen el test transaccional siguiente (pasó en el PR #38).
- SQLite ignora `select_for_update`: los errores de bloqueo solo salen en el job `pytest-postgres` (PR #39: no se puede bloquear el lado opcional de un `select_related`; usar `of=("self",)`). Tampoco reinicia los id entre tests: no asumir números como `AJ-000001` (PR #48).
- Para probar una demo sin tocar `db.sqlite3`: un settings que importa `config.settings` y cambia `DATABASES["default"]["NAME"]`, con `DJANGO_SETTINGS_MODULE` para `seed_demo --fresh` y `runserver` en otro puerto (así se probaron a la vez taller y ferretería en la spec 009).
- El BOM del CSV se escribe con `String.fromCharCode(0xfeff)`: el escape `\uFEFF` puede acabar guardado como carácter invisible. Para comprobarlo, leer los bytes: `Blob.text()` quita el BOM.

## Próximos pasos
- **Spec 005 (facturación DIAN)** aprobada (PR #36) y en curso: T1 (exento/excluido y clientes), T2 (numeración por caja) y T3 (documentos y notas con proveedor simulado; interruptor `INVOICING_ENABLED` apagado) T4 (cola de envío y bandeja DIAN) T5 (contingencia con bloques de números por caja) y T6 (cliente en caja, tiquete de 80 mm con QR y correo) hechas. Faltan T7 (proveedor real) y T8 (prueba de punta a punta). Proveedores comparados en `specs/005-facturacion-dian/proveedores.md`: varios que dicen ser proveedor autorizado no están en el listado oficial de la DIAN; verificar siempre. Decisiones (2026-10-17): proveedor tecnológico por API con adaptador, DE-POS a consumidor final y factura a pedido, contingencia sin conexión, tiquete de 80 mm con QR. Falta elegir el proveedor (decisión comercial) y confirmar con el contador las devoluciones parciales de un DE-POS.
- Primer despliegue real: servidor con dominio y HTTPS (este equipo no tiene Docker; el despliegue solo se prueba en el CI). Cómo probar en un celular: docs/despliegue.md.
- Admin de Django: etiquetas en español (`verbose_name`) y booleanos de solo lectura que muestran el texto de ayuda en vez de Sí/No.
