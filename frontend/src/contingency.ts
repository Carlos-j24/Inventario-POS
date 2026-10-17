// Números de contingencia (spec 005, T5): con conexión, el POS reserva bloques de números de la
// resolución de contingencia de su caja; sin conexión, numera con ellos el tiquete de cada venta.
// Sin React ni IndexedDB para poder probarlo; kvBlockStore lo guarda en el navegador.
import { kv } from "./idb";

export interface ContingencyBlock {
  prefix: string;
  start: number;
  end: number;
  /** Siguiente número sin usar del bloque. */
  next: number;
}

export interface BlockStore {
  get(register: number): Promise<ContingencyBlock[] | undefined>;
  set(register: number, blocks: ContingencyBlock[]): Promise<void>;
}

export const kvBlockStore: BlockStore = {
  get: (register) => kv.get<ContingencyBlock[]>(`contingency:${register}`),
  set: (register, blocks) => kv.set(`contingency:${register}`, blocks),
};

/** Por debajo de esto, el POS reserva otro bloque mientras tenga conexión. */
export const LOW_WATER = 10;

export function remaining(blocks: ContingencyBlock[]): number {
  return blocks.reduce((sum, b) => sum + Math.max(b.end - b.next + 1, 0), 0);
}

/** Con conexión: descarta los bloques agotados y reserva otro si quedan pocos. Devuelve si reservó. */
export async function ensureBlocks(
  store: BlockStore,
  register: number,
  reserve: () => Promise<{ prefix: string; start: number; end: number }>,
): Promise<boolean> {
  const blocks = ((await store.get(register)) ?? []).filter((b) => b.next <= b.end);
  if (remaining(blocks) >= LOW_WATER) {
    await store.set(register, blocks);
    return false;
  }
  const block = await reserve();
  await store.set(register, [...blocks, { ...block, next: block.start }]);
  return true;
}

/** Sin conexión: el siguiente número para el tiquete, o null si el equipo no tiene bloque. */
export async function takeContingencyNumber(store: BlockStore, register: number): Promise<{ number: number; code: string } | null> {
  const blocks = (await store.get(register)) ?? [];
  const block = blocks.find((b) => b.next <= b.end);
  if (!block) return null;
  const number = block.next;
  block.next += 1;
  await store.set(register, blocks);
  return { number, code: `${block.prefix}${number}` };
}
