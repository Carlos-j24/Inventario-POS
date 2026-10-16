# MEMORY.md — Inventario-POS
Memoria del proyecto entre sesiones. Máximo ~50 líneas: resume o elimina lo que ya no aporte.

## Estado actual
- Spec 001, T1–T7 (2026-10-15/16): backend completo. Roles y permisos, catálogo con presentaciones, kardex, ventas con IVA incluido, caja con pago mixto y arqueo, anulaciones y devoluciones, sesión en cookie y API de usuarios. 92 tests de pytest.
- T8 (2026-10-16): frontend React + Vite + TS con Caja, Entradas y Existencias, probado de punta a punta en el navegador.
- T9 (2026-10-16): modo sin conexión (cola de ventas en IndexedDB, sincronización idempotente), service worker y manifest, y bandeja de revisión. Probado apagando los servidores: la venta quedó en cola y llegó una sola vez. 97 tests de pytest y 25 de Vitest.
- T10 (2026-10-16): Docker (gunicorn + WhiteNoise, un contenedor) + PostgreSQL. Guía en docs/despliegue.md. **Spec 001 (MVP) completa.**
- Repositorio público Carlos-j24/Inventario-POS. El CI corre pytest (3.12 y 3.14), el frontend (tipos, Vitest, build) y la imagen de Docker con PostgreSQL (`scripts/smoke-test.sh`) en cada PR.

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
- `gh pr merge --auto` sin checks obligatorios en la rama fusiona AL INSTANTE, aunque el CI siga corriendo (pasó con el PR #8, 2026-10-16). Desde entonces main exige los cuatro checks y el repo tiene `allow_auto_merge`. Con los PR #9 y #10 GitHub no disparó la fusión al quedar todo en verde (con el #11 sí): revisar y fusionar a mano si pasa.
- Bases de desarrollo con ventas anteriores a la T5 no migran (las ventas exigen turno): borrar `db.sqlite3` y volver a migrar.

## Próximos pasos
- Verificado (2026-10-16): Chrome de escritorio y Android (OPPO Reno13 F) abren sin conexión y se instalan con el ícono SVG. Cómo probar en un celular: docs/despliegue.md.
- Este equipo no tiene Docker: el despliegue solo se ha probado en el CI. Primer despliegue real: servidor con dominio y HTTPS.
- Spec 002 (pedidos vendedor → caja) escrita y con decisiones cerradas (2026-10-16): precio del pedido, vence al final del día, código de 4 dígitos, stock solo avisa. Aprobada; T1 (modelos y `Sale.salesperson`) hecha. Después, en orden de prioridad del equipo: pantallas de supervisor/admin, reportes, facturación DIAN.
- Pantallas que faltan en la PWA: devoluciones/anulaciones (supervisor) y administración de usuarios (hoy por el admin de Django).
- Admin: etiquetas en español (`verbose_name`) y booleanos de solo lectura que muestran el texto de ayuda en vez de Sí/No.
