# MEMORY.md — Inventario-POS
Memoria del proyecto entre sesiones. Máximo ~50 líneas: resume o elimina lo que ya no aporte.

## Estado actual
- 2026-10-15: esqueleto del backend (spec 001, tareas T1 a T3). Usuarios, roles y permisos; catálogo con unidades y presentaciones; inventario con kardex, entradas por API y existencias. 21 tests en verde.
- 2026-10-15: T4 ventas: venta + líneas + salida de stock en una transacción, IVA incluido separado por línea, idempotente. 36 tests en verde.
- 2026-10-15: repositorio público Carlos-j24/Inventario-POS. CI (GitHub Actions) con pytest en Python 3.12 y 3.14 en cada PR: no fusionar con el CI en rojo.
- 2026-10-16: T5 caja: turnos por caja física, pago mixto con vueltas, arqueo al cierre. Las ventas ahora exigen turno y pagos. 55 tests en verde.
- 2026-10-16: T6 anulaciones (venta completa, turno abierto) y devoluciones parciales con reembolso. 71 tests en verde.
- Falta: autenticación, frontend PWA y sincronización sin conexión (ver `specs/001-mvp/tasks.md`).

## Decisiones (y por qué)
- AGENTS.md es la fuente única de reglas; CLAUDE.md solo lo importa → mismas reglas para Claude Code y OpenCode.
- Primer cliente: ferretería → unidades con conversión (rollo/metro) y venta fraccionada desde el MVP. Lotes y vencimientos quedan para cuando llegue una droguería.
- Stock como libro de movimientos + saldo cacheado y bloqueado (`select_for_update`) → kardex auditable y sin carreras entre cajas.
- Modo sin conexión: el POS genera UUID por documento y se sincroniza con reintentos idempotentes; puede dejar stock negativo (`needs_review`) antes que bloquear una venta.
- Roles editables y permisos fijos por código → el admin crea roles nuevos sin tocar el código.
- Precios con IVA incluido → así se exhiben en ferretería; el POS suma totales y el backend separa la base y el IVA.
- Turno por caja física, no por cajero (decisión del equipo, 2026-10-16) → el arqueo cuadra el cajón; si cambia el cajero, se cierra y se abre otro turno.
- Pago mixto permitido (decisión del equipo) → tarjeta y transferencia no pueden pasarse del total; el efectivo da vueltas.

## Aprendizajes y errores a evitar
- Tests con pytest-django: `manage.py test` no los encuentra (DevForge Init lo propone por defecto al detectar Django).
- Al meter fallos a propósito: quitar la consulta previa de `client_uuid` no rompe nada, porque la restricción única de la base de datos ya protege contra duplicados.
- Un test de redondeo con precios "redondos" (3.200) no prueba nada: el centavo perdido solo aparece con precios con centavos (3.199,99).
- Bases de desarrollo con ventas anteriores a la T5 no migran (las ventas exigen turno): borrar `db.sqlite3` y volver a migrar.

## Próximos pasos
- T7: autenticación para la PWA (sesión con cookie o JWT) y API de usuarios y roles para el administrador.
- Admin: etiquetas en español (`verbose_name`) y booleanos de solo lectura que muestran el texto de ayuda en vez de Sí/No.
