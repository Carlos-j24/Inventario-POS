# Tareas — Spec 008

> Borrador con las decisiones (2026-10-22). Se empieza a programar cuando se apruebe el PR de la spec.

- [ ] **T1** Backend: `Warehouse.is_default` con restricción de una sola principal; marcar otra desmarca la anterior y desactivar la principal le quita la marca (en el modelo, así vale para el admin y para cualquier código). Migración de datos: `PRAL` o la primera activa por código. `/api/inventory/warehouses/` con `is_default` y la principal primero. `seed_demo` deja `PRAL` como principal. (Reglas 1 a 3)
- [ ] **T2** Frontend: `warehouse.ts` con la regla de qué proponer (recordada si sigue activa → principal → primera) y lo que se recuerda por usuario en `localStorage`; Entradas, Ajustes y Conteos la usan y recuerdan lo que se elige; Traslados propone origen y destino según la regla. (Reglas 4 a 6)
- [ ] **T3** Prueba en el navegador con la demo (dos usuarios en el mismo equipo, bodega recordada, bodega desactivada) y cierre: `docs/arquitectura.md`, `MEMORY.md` y la spec.
