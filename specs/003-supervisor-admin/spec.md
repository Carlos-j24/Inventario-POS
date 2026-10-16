# Spec 003 — Pantallas de supervisor y administrador

> Estado: ✅ **completada (2026-10-16)**. Tareas en tasks.md (T1–T7, PRs #22–#28).

## Problema
El backend ya sabe anular, devolver y gestionar usuarios y roles (specs 001 y 002), pero **no hay pantallas**: el supervisor y el administrador dependen del admin de Django o de la API. En la ferretería, cuando un cliente devuelve un producto o el cajero se equivoca, el supervisor no tiene cómo hacerlo desde la app, y el administrador no puede dar de alta a un empleado sin entrar al admin técnico.

## Objetivo
Dos pantallas nuevas en la app, según permisos:
- **Ventas** (supervisor, `sales.void`): buscar una venta, ver su detalle y **anularla** o hacer una **devolución**.
- **Usuarios** (administrador, `users.manage`): crear usuarios, asignar roles, desactivar, cambiar contraseñas y editar los permisos de cada rol.

Además, **cualquier usuario puede cambiar su propia contraseña**.

## Historias
1. **Como supervisor** busco una venta por su número (`V-000123`) o veo las de hoy filtradas por caja, y abro su detalle: líneas, pagos, quién vendió, quién cobró, devoluciones previas y si está marcada para revisión.
2. **Como supervisor** anulo una venta completa con motivo, si su turno sigue abierto. Si ya cerró, la pantalla me ofrece hacer una devolución.
3. **Como supervisor** hago una devolución: elijo las líneas y cantidades (sin pasar de lo vendido menos lo ya devuelto), el motivo, el medio del reembolso y la caja de donde sale el dinero.
4. **Como supervisor**, desde la bandeja de revisión, abro el detalle de la venta para anularla o devolverla si hace falta.
5. **Como administrador** veo la lista de usuarios con sus roles y si están activos. Creo uno nuevo con contraseña inicial y roles, cambio sus roles, lo desactivo o lo reactivo, y le pongo una contraseña nueva si la olvidó.
6. **Como administrador** veo los roles con sus permisos (en lenguaje claro), creo un rol nuevo y marco o desmarco permisos.
7. **Como cualquier usuario** cambio mi contraseña escribiendo la actual y la nueva.

## Reglas (ya existen en el backend; la pantalla las respeta y las explica)
- Anular: venta completa, solo con su turno abierto y sin devoluciones previas; el stock vuelve y los pagos salen del arqueo.
- Devolver: en cualquier momento, sin pasar de lo vendido; el reembolso sale de un **turno abierto**; el arqueo de turnos cerrados no cambia.
- Usuarios: no se borran, se desactivan; nadie se desactiva a sí mismo; siempre queda al menos un usuario activo con `users.manage`; contraseñas con los validadores de Django.

## Lo que falta en el backend
- `GET /api/sales/` para buscar y listar ventas: por número, por fecha, por caja y por estado (permiso `sales.void` o `reports.view`).
- `POST /api/auth/password/` para cambiar la contraseña propia (pide la actual) y la marca `must_change_password` (decisión 3).
- El detalle de la venta (`GET /api/sales/<id>/`) debe incluir las devoluciones hechas y lo ya devuelto por línea. Hoy exige `sales.create`; pasa a `sales.create` o `sales.void` o `reports.view`.

## Decisiones (equipo, 2026-10-16)
1. **Autorización: en la pantalla del supervisor**, con su propia sesión. Si la devolución reembolsa dinero, el supervisor elige de qué **caja con turno abierto** sale. La autorización con clave en la caja del cajero queda para más adelante.
2. **Listado: las ventas de hoy** (fecha de negocio, hora de Bogotá), de la más reciente a la más antigua, con filtro por caja y estado. Las de otros días se buscan por número o por fecha.
3. **Contraseña inicial: temporal, con cambio obligatorio.** Cuando el administrador crea un usuario o le pone una contraseña nueva, el usuario queda marcado (`must_change_password`). Al iniciar sesión, la app le pide cambiarla antes de mostrar nada más, y **la API solo le permite** consultar quién es, cambiar la contraseña y salir. Así el administrador nunca conoce la clave definitiva.
4. **Roles: todos editables desde la app**, también los que vienen por defecto. Sigue la protección de que siempre quede al menos un usuario activo con `users.manage`.

## Fuera de esta spec
Reportes, ajustes de inventario y conteos físicos en la app, auditoría de cambios de usuarios, autenticación en dos pasos.

## Criterios de aceptación
- Un usuario sin `sales.void` no ve la pantalla Ventas, y la API le responde 403.
- Una devolución desde la pantalla no permite pasar de lo vendido menos lo ya devuelto.
- Anular una venta con el turno cerrado no es posible desde la pantalla, que explica por qué y ofrece la devolución.
- Un administrador puede dar de alta un usuario con rol Caja, y ese usuario puede iniciar sesión y vender.
- Nadie puede quitarse a sí mismo el último acceso de administrador desde la pantalla.
- Un usuario con contraseña temporal no puede usar la API (salvo quién soy, cambiar contraseña y salir) hasta cambiarla.
- Una devolución con reembolso en efectivo aparece en el arqueo de la caja elegida.
