# Tareas — Spec 009

> Spec en borrador (2026-10-27). Decisiones en spec.md.

- [ ] **T1** Backend, modelo: casilla `Business.workshop_enabled`; app `workshop` con `Motorcycle` (placa y chasis normalizados y únicos, chasis obligatorio sin placa, kilometraje que solo sube salvo con nota) y `Ownership` (dueño desde/hasta; cambiar de dueño cierra el anterior). Permiso `workshop.receive` y rol "Recepción de taller" en una migración. Admin de motos. (Reglas 1, 2, 5, 6, 7 y 9)
- [ ] **T2** API: `/api/workshop/motorcycles/` para buscar (placa, chasis, documento, nombre o teléfono del dueño), registrar con cliente existente o nuevo, corregir, actualizar el kilometraje y cambiar de dueño; 404 con el módulo apagado. Búsqueda de clientes por teléfono y teléfono obligatorio desde el taller. `/api/auth/me/` dice si el módulo está activo. (Reglas 1, 3, 4, 7 y 8)
- [ ] **T3** Frontend: pantalla "Motos" (buscar, ficha con dueño e historial, registrar moto con cliente nuevo o existente, corregir, kilometraje, cambio de dueño), visible solo con el módulo activo y el permiso. (Reglas 5 a 8)
- [ ] **T4** `seed_demo --taller`: módulo activo, catálogo de repuestos de moto, clientes y motos de ejemplo (una con dueño anterior y una sin placa). (Regla 10)
- [ ] **T5** Prueba en el navegador con la demo de taller y con la de ferretería (módulo apagado), y cierre: `docs/arquitectura.md`, `MEMORY.md` y la spec.
