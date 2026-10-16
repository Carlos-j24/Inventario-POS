# Constitución — Inventario-POS

Principios que ninguna spec ni cambio puede romper.

1. **El inventario cuadra siempre.** El stock de un producto es la suma de sus movimientos. Ningún proceso cambia existencias sin dejar un movimiento con usuario, fecha y documento de origen.
2. **Nada se borra.** Ventas, movimientos y cierres de caja se anulan o corrigen con un documento nuevo, nunca se editan ni se eliminan.
3. **La caja no se detiene.** Si se cae internet, el POS sigue vendiendo y cobrando. Es preferible un descuadre que hay que revisar a un cliente sin atender.
4. **Permisos en el servidor.** El frontend puede ocultar botones, pero quien decide es el backend, con permisos y no con nombres de rol.
5. **Dinero exacto.** Cantidades y valores con decimales exactos (`Decimal`/`NUMERIC`), con el IVA calculado por línea.
6. **Probado antes de darlo por hecho.** Cada regla de negocio tiene su test; si un test pasa a la primera, se comprueba metiendo un fallo a propósito.
