# Tareas — Spec 008

> Spec aprobada (PR #64, 2026-10-22). Decisiones en spec.md.

- [x] **T1** Backend: `Warehouse.is_default` con restricción de una sola principal; marcar otra desmarca la anterior y desactivar la principal le quita la marca (en el modelo, así vale para el admin y para cualquier código). Migración de datos: `PRAL` o la primera activa por código. `/api/inventory/warehouses/` con `is_default` y la principal primero. `seed_demo` deja `PRAL` como principal. (Reglas 1 a 3)
  - `Warehouse.save` hace cumplir las dos reglas (también con `update_fields`), y dos restricciones de la base de datos las garantizan aunque alguien se salte `save`. Admin con la columna "principal". En la base de demostración la migración marcó `PRAL`. 9 tests y 8 fallos a propósito.
- [ ] **T2** Frontend: `warehouse.ts` con la regla de qué proponer (recordada si sigue activa → principal → primera) y lo que se recuerda por usuario en `localStorage`; Entradas, Ajustes y Conteos la usan y recuerdan lo que se elige; Traslados propone origen y destino según la regla. (Reglas 4 a 6)
- [ ] **T3** Prueba en el navegador con la demo (dos usuarios en el mismo equipo, bodega recordada, bodega desactivada) y cierre: `docs/arquitectura.md`, `MEMORY.md` y la spec.
