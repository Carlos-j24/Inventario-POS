# MEMORY.md — Inventario-POS
Memoria del proyecto entre sesiones. Máximo ~50 líneas: resume o elimina lo que ya no aporte.

## Estado actual (2026-10-17)
- **Spec 001 (MVP)** completa: backend (roles, catálogo, kardex, ventas con IVA incluido, caja con pago mixto y arqueo, devoluciones, sesión en cookie), frontend React con modo sin conexión e instalable, y despliegue Docker + PostgreSQL.
- **Spec 002 (pedidos vendedor → caja)** completa: el vendedor arma el pedido con un código de 4 dígitos y la caja lo cobra; la venta guarda quién vendió y quién cobró.
- **Spec 003 (supervisor y administrador)** completa: pantallas Ventas (buscar, anular, devolver), Usuarios, Roles, cambiar mi contraseña y contraseña temporal con cambio obligatorio (la API bloquea hasta cambiarla).
- **Spec 004 (reportes)** completa: costo promedio ponderado guardado en cada salida, pantalla Reportes (ventas, productos, arqueos; inventario valorizado y márgenes con `reports.costs`) y CSV para Excel.
- Repositorio público Carlos-j24/Inventario-POS. main exige 5 checks: pytest 3.12 y 3.14, pytest-postgres, frontend y docker (`scripts/smoke-test.sh`).

## Decisiones (y por qué)
- AGENTS.md es la fuente única de reglas; CLAUDE.md solo lo importa → mismas reglas para Claude Code y OpenCode.
- Primer cliente: ferretería → unidades con conversión (rollo/metro) y venta fraccionada desde el MVP. Lotes y vencimientos quedan para cuando llegue una droguería.
- Stock como libro de movimientos + saldo cacheado y bloqueado (`select_for_update`) → kardex auditable y sin carreras entre cajas.
- Modo sin conexión: el POS genera UUID por documento y se sincroniza con reintentos idempotentes; puede dejar stock negativo (`needs_review`) antes que bloquear una venta.
- Roles editables y permisos fijos por código → el admin crea roles nuevos sin tocar el código.
- Precios con IVA incluido → así se exhiben en ferretería; el POS suma totales y el backend separa la base y el IVA.
- Turno por caja física, no por cajero (decisión del equipo, 2026-10-16) → el arqueo cuadra el cajón; si cambia el cajero, se cierra y se abre otro turno.
- Sesión en cookie y no JWT → sin dependencias nuevas y la cookie HttpOnly no la lee JavaScript; obliga a servir la PWA y la API desde el mismo dominio.
- gunicorn + WhiteNoise en un solo contenedor (decisión del equipo, 2026-10-16) → más simple que nginx aparte; HTTPS lo pone un proxy delante (Caddy).
- Pago mixto permitido (decisión del equipo) → tarjeta y transferencia no pueden pasarse del total; el efectivo da vueltas.

## Aprendizajes y errores a evitar
- Tests con pytest-django: `manage.py test` no los encuentra (DevForge Init lo propone por defecto al detectar Django).
- Al meter fallos a propósito: quitar la consulta previa de `client_uuid` no rompe nada, porque la restricción única de la base de datos ya protege contra duplicados.
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
- SQLite ignora `select_for_update`: los errores de bloqueo solo salen en el job `pytest-postgres` (PR #39: no se puede bloquear el lado opcional de un `select_related`; usar `of=("self",)`).
- Bases de desarrollo con ventas anteriores a la T5 no migran (las ventas exigen turno): borrar `db.sqlite3` y volver a migrar.
- El BOM del CSV se escribe con `String.fromCharCode(0xfeff)`: el escape `\uFEFF` puede acabar guardado como carácter invisible. Para comprobarlo, leer los bytes: `Blob.text()` quita el BOM.

## Próximos pasos
- **Spec 005 (facturación DIAN)** aprobada (PR #36) y en curso: T1 (exento/excluido y clientes), T2 (numeración por caja) y T3 (documentos y notas con proveedor simulado; interruptor `INVOICING_ENABLED` apagado) T4 (cola de envío y bandeja DIAN) T5 (contingencia con bloques de números por caja) y T6 (cliente en caja, tiquete de 80 mm con QR y correo) hechas. Faltan T7 (proveedor real) y T8 (prueba de punta a punta). Proveedores comparados en `specs/005-facturacion-dian/proveedores.md`: varios que dicen ser proveedor autorizado no están en el listado oficial de la DIAN; verificar siempre. Decisiones (2026-10-17): proveedor tecnológico por API con adaptador, DE-POS a consumidor final y factura a pedido, contingencia sin conexión, tiquete de 80 mm con QR. Falta elegir el proveedor (decisión comercial) y confirmar con el contador las devoluciones parciales de un DE-POS.
- Primer despliegue real: servidor con dominio y HTTPS (este equipo no tiene Docker; el despliegue solo se prueba en el CI). Cómo probar en un celular: docs/despliegue.md.
- Admin de Django: etiquetas en español (`verbose_name`) y booleanos de solo lectura que muestran el texto de ayuda en vez de Sí/No.
