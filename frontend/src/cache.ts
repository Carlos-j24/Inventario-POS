// Datos de lectura con copia local: se piden al servidor y, si no hay red, se usa la última copia.
import { api } from "./api";
import { kv } from "./idb";
import { isUnreachable } from "./offline";

export interface Cached<T> {
  data: T;
  /** Fecha de la copia local si el servidor no respondió; null si los datos son frescos. */
  staleSince: string | null;
}

export async function fetchWithCache<T>(path: string): Promise<Cached<T>> {
  const key = `cache:${path}`;
  try {
    const data = await api<T>(path);
    kv.set(key, { data, savedAt: new Date().toISOString() }).catch(() => {});
    return { data, staleSince: null };
  } catch (err) {
    if (!isUnreachable(err)) throw err;
    const saved = await kv.get<{ data: T; savedAt: string }>(key).catch(() => undefined);
    if (!saved) throw new Error("Sin conexión y sin copia local: conecta este equipo una vez para descargar los datos.");
    return { data: saved.data, staleSince: saved.savedAt };
  }
}
