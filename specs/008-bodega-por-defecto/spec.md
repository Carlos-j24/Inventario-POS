# Spec 008 — Bodega por defecto

> Estado: **borrador con decisiones cerradas (2026-10-22)**; pendiente aprobar el PR para empezar a programar. Tareas en tasks.md.

## Problema
Con más de una bodega, todas las pantallas de inventario proponen **la primera por código**: Entradas, Ajustes, Conteos y Traslados toman `ws[0]` de `/api/inventory/warehouses/`, que viene ordenada por código. En la base de demostración, con `PRAL` (Bodega principal) y `LOC` (Local), cada pantalla proponía "Local" y había que elegir la principal a mano cada vez. Lo encontró la prueba de punta a punta de la spec 006 (T9).

Además de ser incómodo, es un riesgo: una entrada o una baja registrada en la bodega equivocada descuadra las dos bodegas, y nadie se da cuenta hasta el siguiente conteo.

## Objetivo
Que cada pantalla proponga la bodega correcta: la que se usó la última vez en ese equipo o, si no hay, la **bodega principal** que marca el administrador.

## Reglas
- **Bodega principal**: una casilla en la bodega (admin de Django). Solo una puede estar marcada: marcar otra desmarca la anterior. La principal tiene que estar activa: desactivarla le quita la marca.
- La migración marca como principal la que tenga el código `PRAL` si existe y, si no, la primera activa por código. Si no hay bodegas, no marca ninguna.
- `/api/inventory/warehouses/` devuelve `is_default` y trae la principal primero (luego, por código).
- **Qué propone cada pantalla**, en este orden:
  1. la última bodega que eligió **ese usuario en ese equipo**, si sigue activa (`localStorage`, por usuario: en una caja compartida cada quien tiene la suya);
  2. si no, la principal;
  3. si no hay principal, la primera de la lista.
- Se recuerda lo que el usuario elige en Entradas, Ajustes y Conteos (es la misma preferencia para las tres).
- **Traslados**: el origen sigue esa misma regla; el destino es la principal si el origen no lo es y, si lo es, la primera otra bodega. El destino no se recuerda: un traslado es una excepción, no la rutina.
- Nada de esto cambia la Caja: la caja ya tiene su bodega (spec 001) y ya recuerda la caja elegida en el equipo.
- Sin permisos nuevos y sin librerías nuevas.

## Decisiones (2026-10-22)
1. **La bodega por defecto es una "bodega principal" marcada en el admin**, una sola para todos. _Descartadas:_ una bodega por usuario (más flexible, pero hay que configurarla a cada uno) y la bodega de la caja abierta (no sirve para bodega, que no abre caja).
2. **Se recuerda la última bodega elegida por cada usuario en cada equipo** (en el navegador, como ya se recuerda la caja). La principal queda para la primera vez y para quien no ha elegido. _Descartada:_ arrancar siempre en la principal.

## Criterios de aceptación
- Con `LOC` y `PRAL`, una base nueva propone `PRAL` en Entradas, Ajustes, Conteos y como origen de Traslados (con `LOC` de destino).
- Si Pedro elige `LOC` en Entradas, la próxima vez Entradas, Ajustes y Conteos le proponen `LOC` en ese equipo; a Marta, en el mismo equipo, le siguen proponiendo `PRAL`.
- Si se desactiva la bodega recordada, se propone la principal.
- Nunca hay dos bodegas principales, ni una principal inactiva.
- `seed_demo` deja `PRAL` como principal.
