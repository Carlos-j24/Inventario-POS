import { describe, expect, it, vi } from "vitest";

import { ensureBlocks, LOW_WATER, remaining, takeContingencyNumber, type BlockStore, type ContingencyBlock } from "./contingency";

function memoryStore(initial: Record<number, ContingencyBlock[]> = {}): BlockStore & { saved: Record<number, ContingencyBlock[]> } {
  const saved = { ...initial };
  return {
    saved,
    get: async (register) => structuredClone(saved[register]), // como IndexedDB: una copia
    set: async (register, blocks) => { saved[register] = blocks; },
  };
}

const block = (start: number, end: number, next = start): ContingencyBlock => ({ prefix: "CT1", start, end, next });

describe("bloques de contingencia", () => {
  it("cuenta lo que queda en todos los bloques", () => {
    expect(remaining([block(1, 50, 41), block(51, 100)])).toBe(60);
    expect(remaining([block(1, 50, 51)])).toBe(0);
  });

  it("reserva cuando no hay bloque o quedan menos de 10, y descarta los agotados", async () => {
    const store = memoryStore({ 3: [block(1, 50, 51), block(51, 60, 52)] }); // 9 libres
    const reserve = vi.fn().mockResolvedValue({ prefix: "CT1", start: 101, end: 150 });
    expect(await ensureBlocks(store, 3, reserve)).toBe(true);
    expect(store.saved[3]).toEqual([block(51, 60, 52), block(101, 150)]);
    expect(await ensureBlocks(store, 3, reserve)).toBe(false); // ya hay de sobra
    expect(reserve).toHaveBeenCalledTimes(1);
    expect(LOW_WATER).toBe(10);
  });

  it("con exactamente 10 libres no reserva", async () => {
    const reserve = vi.fn();
    expect(await ensureBlocks(memoryStore({ 3: [block(1, 10)] }), 3, reserve)).toBe(false);
    expect(reserve).not.toHaveBeenCalled();
    expect(await ensureBlocks(memoryStore(), 4, vi.fn().mockResolvedValue({ prefix: "X", start: 1, end: 5 }))).toBe(true);
  });

  it("numera en orden, salta al bloque siguiente y devuelve null al agotarse", async () => {
    const store = memoryStore({ 3: [block(1, 2, 2), block(51, 51)] });
    expect(await takeContingencyNumber(store, 3)).toEqual({ number: 2, code: "CT12" });
    expect(await takeContingencyNumber(store, 3)).toEqual({ number: 51, code: "CT151" });
    expect(await takeContingencyNumber(store, 3)).toBeNull();
    expect(await takeContingencyNumber(store, 9)).toBeNull(); // otra caja: sin bloques
  });
});
