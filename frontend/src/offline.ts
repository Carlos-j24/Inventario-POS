// Ventas sin conexión: la cola y su sincronización, sin React ni IndexedDB para poder probarlas.
// Reglas (docs/arquitectura.md):
// - Cada venta lleva su client_uuid: reenviarla nunca la duplica.
// - Una venta en cola va con offline=true y el precio cobrado en cada línea.
// - Solo se envían las ventas del usuario con sesión: el vendedor de cada venta debe ser quien la hizo.
import { ApiError } from "./api";

export interface QueuedSale {
  client_uuid: string;
  username: string;
  createdAt: string;
  totalCents: number;
  body: Record<string, unknown>;
  status: "pending" | "failed";
  error?: string;
  /** Número del tiquete de contingencia (spec 005, T5), si el equipo tenía bloque. */
  contingencyCode?: string;
}

export interface OutboxStore {
  all(): Promise<QueuedSale[]>;
  put(item: QueuedSale): Promise<void>;
  remove(id: string): Promise<void>;
}

/** Sin red o servidor caído: vale la pena reintentar más tarde. */
export function isUnreachable(err: unknown): boolean {
  if (err instanceof TypeError) return true; // fetch falla sin red
  if (err instanceof DOMException && (err.name === "TimeoutError" || err.name === "AbortError")) return true;
  return err instanceof ApiError && [0, 502, 503, 504].includes(err.status);
}

export interface SyncResult {
  sent: number;
  failed: number;
  stopped: "offline" | "auth" | null;
}

/**
 * Envía en orden las ventas pendientes del usuario. Se detiene sin red o si la sesión venció
 * (el cajero vuelve a iniciar sesión y se reintenta). Si el servidor rechaza una venta (400),
 * queda como "failed" para que alguien la revise: no se reintenta en bucle.
 */
export async function syncOutbox(
  store: OutboxStore,
  username: string,
  send: (body: Record<string, unknown>) => Promise<unknown>,
): Promise<SyncResult> {
  const result: SyncResult = { sent: 0, failed: 0, stopped: null };
  const items = (await store.all())
    .filter((i) => i.username === username && i.status === "pending")
    .sort((a, b) => a.createdAt.localeCompare(b.createdAt));
  for (const item of items) {
    try {
      await send(item.body);
      await store.remove(item.client_uuid);
      result.sent++;
    } catch (err) {
      if (isUnreachable(err)) {
        result.stopped = "offline";
        break;
      }
      if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
        result.stopped = "auth";
        break;
      }
      await store.put({ ...item, status: "failed", error: (err as Error).message });
      result.failed++;
    }
  }
  return result;
}

/** El mismo cuerpo de una venta en línea, marcado como sin conexión y con el precio cobrado. */
export function toOfflineBody(body: Record<string, unknown>, unitPricesCents: number[]): Record<string, unknown> {
  const lines = (body.lines as Record<string, unknown>[]).map((line, i) => ({
    ...line,
    unit_price: (unitPricesCents[i] / 100).toFixed(2),
  }));
  return { ...body, offline: true, occurred_at: new Date().toISOString(), lines };
}
