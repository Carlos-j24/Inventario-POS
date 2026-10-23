// Qué bodega proponen las pantallas de inventario (spec 008), sin React para poder probarlo.
// La API trae solo las activas, con la principal primero.
import type { Warehouse } from "./api";

const key = (username: string) => `inventario.bodega.${username}`;

/** La última bodega que eligió este usuario en este equipo (cada quien la suya en un equipo compartido). */
export function rememberedWarehouse(username: string | undefined): number | null {
  if (!username) return null;
  try {
    const value = Number(localStorage.getItem(key(username)));
    return Number.isInteger(value) && value > 0 ? value : null;
  } catch {
    return null; // sin almacenamiento local solo se pierde la comodidad de recordarla
  }
}

export function rememberWarehouse(username: string | undefined, id: number | null) {
  if (!username || id == null) return;
  try {
    localStorage.setItem(key(username), String(id));
  } catch {
    /* sin almacenamiento local: no se recuerda */
  }
}

/** La recordada si sigue activa; si no, la principal; si no hay principal, la primera. */
export function proposeWarehouse(warehouses: Warehouse[], remembered: number | null): number | null {
  if (remembered != null && warehouses.some((w) => w.id === remembered)) return remembered;
  return (warehouses.find((w) => w.is_default) ?? warehouses[0])?.id ?? null;
}

/** Traslado: el origen como en las demás pantallas; el destino, la principal o, si el origen ya lo es, otra. */
export function proposeTransfer(warehouses: Warehouse[], remembered: number | null): { origin: number | null; destination: number | null } {
  const origin = proposeWarehouse(warehouses, remembered);
  const others = warehouses.filter((w) => w.id !== origin);
  const destination = (others.find((w) => w.is_default) ?? others[0])?.id ?? null;
  return { origin, destination };
}
