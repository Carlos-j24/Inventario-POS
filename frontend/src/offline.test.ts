import { describe, expect, it, vi } from "vitest";

import { ApiError } from "./api";
import { isUnreachable, syncOutbox, toOfflineBody, type OutboxStore, type QueuedSale } from "./offline";

function memoryStore(items: QueuedSale[]): OutboxStore & { items: Map<string, QueuedSale> } {
  const map = new Map(items.map((i) => [i.client_uuid, i]));
  return {
    items: map,
    all: async () => [...map.values()],
    put: async (i) => void map.set(i.client_uuid, i),
    remove: async (id) => void map.delete(id),
  };
}

const sale = (id: string, username = "laura", createdAt = `2026-10-16T10:0${id}:00Z`): QueuedSale => ({
  client_uuid: id, username, createdAt, totalCents: 100, body: { client_uuid: id }, status: "pending",
});

describe("isUnreachable", () => {
  it("distingue red caída de errores del servidor", () => {
    expect(isUnreachable(new TypeError("Failed to fetch"))).toBe(true);
    expect(isUnreachable(new ApiError(503, "x"))).toBe(true);
    expect(isUnreachable(new DOMException("lento", "TimeoutError"))).toBe(true);
    expect(isUnreachable(new ApiError(400, "x"))).toBe(false);
    expect(isUnreachable(new ApiError(403, "x"))).toBe(false);
    expect(isUnreachable(new Error("x"))).toBe(false);
  });
});

describe("syncOutbox", () => {
  it("envía en orden de creación y vacía la cola", async () => {
    const store = memoryStore([sale("2"), sale("1")]);
    const send = vi.fn().mockResolvedValue({});
    const r = await syncOutbox(store, "laura", send);
    expect(send.mock.calls.map((c) => c[0].client_uuid)).toEqual(["1", "2"]);
    expect(r).toEqual({ sent: 2, failed: 0, stopped: null });
    expect(store.items.size).toBe(0);
  });

  it("solo envía las ventas del usuario con sesión", async () => {
    const store = memoryStore([sale("1", "laura"), sale("2", "andres")]);
    const send = vi.fn().mockResolvedValue({});
    await syncOutbox(store, "laura", send);
    expect(send).toHaveBeenCalledTimes(1);
    expect([...store.items.keys()]).toEqual(["2"]);
  });

  it("sin red se detiene y no pierde nada", async () => {
    const store = memoryStore([sale("1"), sale("2")]);
    const send = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));
    const r = await syncOutbox(store, "laura", send);
    expect(r.stopped).toBe("offline");
    expect(send).toHaveBeenCalledTimes(1);
    expect(store.items.size).toBe(2);
  });

  it("con la sesión vencida se detiene para que el cajero vuelva a entrar", async () => {
    const store = memoryStore([sale("1")]);
    const r = await syncOutbox(store, "laura", vi.fn().mockRejectedValue(new ApiError(403, "No autenticado")));
    expect(r.stopped).toBe("auth");
    expect(store.items.get("1")?.status).toBe("pending");
  });

  it("una venta rechazada queda marcada y no bloquea las demás", async () => {
    const store = memoryStore([sale("1"), sale("2")]);
    const send = vi.fn()
      .mockRejectedValueOnce(new ApiError(400, "Producto inactivo"))
      .mockResolvedValueOnce({});
    const r = await syncOutbox(store, "laura", send);
    expect(r).toEqual({ sent: 1, failed: 1, stopped: null });
    expect(store.items.get("1")).toMatchObject({ status: "failed", error: "Producto inactivo" });
    expect(store.items.has("2")).toBe(false);
    // Las rechazadas no se reintentan solas.
    send.mockClear();
    await syncOutbox(store, "laura", send);
    expect(send).not.toHaveBeenCalled();
  });
});

describe("toOfflineBody", () => {
  it("marca offline, pone el precio cobrado por línea y conserva el resto", () => {
    const body = { client_uuid: "u", shift: 1, lines: [{ product: 2, quantity: "3" }], payments: [] };
    const out = toOfflineBody(body, [2800000]);
    expect(out).toMatchObject({ client_uuid: "u", shift: 1, offline: true, payments: [] });
    expect(out.lines).toEqual([{ product: 2, quantity: "3", unit_price: "28000.00" }]);
    expect(typeof out.occurred_at).toBe("string");
  });
});
