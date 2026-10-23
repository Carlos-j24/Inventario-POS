import { afterEach, describe, expect, it, vi } from "vitest";

import type { Warehouse } from "./api";
import { proposeTransfer, proposeWarehouse, rememberedWarehouse, rememberWarehouse } from "./warehouse";

const pral: Warehouse = { id: 1, code: "PRAL", name: "Bodega principal", is_default: true };
const loc: Warehouse = { id: 2, code: "LOC", name: "Local", is_default: false };
const vit: Warehouse = { id: 3, code: "VIT", name: "Vitrina", is_default: false };

afterEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

describe("proposeWarehouse", () => {
  it("la recordada si sigue activa; si no, la principal; si no hay principal, la primera", () => {
    expect(proposeWarehouse([loc, pral], 2)).toBe(2);
    expect(proposeWarehouse([loc, pral], null)).toBe(1); // la principal aunque no venga primero
    expect(proposeWarehouse([loc, pral], 99)).toBe(1); // la recordada se desactivó
    expect(proposeWarehouse([loc, { ...vit }], null)).toBe(2);
    expect(proposeWarehouse([], 2)).toBeNull();
  });
});

describe("proposeTransfer", () => {
  it("de la recordada hacia la principal", () => {
    expect(proposeTransfer([pral, loc, vit], 2)).toEqual({ origin: 2, destination: 1 });
    expect(proposeTransfer([loc, vit, pral], 3)).toEqual({ origin: 3, destination: 1 }); // aunque la principal no venga primero
  });

  it("si el origen ya es la principal, el destino es la primera otra", () => {
    expect(proposeTransfer([pral, loc, vit], null)).toEqual({ origin: 1, destination: 2 });
    expect(proposeTransfer([loc, vit], null)).toEqual({ origin: 2, destination: 3 }); // sin principal
  });

  it("con una sola bodega no hay destino", () => {
    expect(proposeTransfer([pral], null)).toEqual({ origin: 1, destination: null });
  });
});

describe("lo que se recuerda", () => {
  it("es de cada usuario en este equipo", () => {
    rememberWarehouse("pedro", 2);
    expect(rememberedWarehouse("pedro")).toBe(2);
    expect(rememberedWarehouse("marta")).toBeNull();
    expect(rememberedWarehouse(undefined)).toBeNull();
    rememberWarehouse(undefined, 3); // sin usuario no se guarda nada
    rememberWarehouse("", 3);
    expect(localStorage.length).toBe(1);
    localStorage.setItem("inventario.bodega.undefined", "3");
    expect(rememberedWarehouse(undefined)).toBeNull(); // ni se lee
    rememberWarehouse("pedro", null);
    expect(rememberedWarehouse("pedro")).toBe(2);
  });

  it("un valor raro no cuenta", () => {
    for (const raw of ["abc", "0", "-3", "2.5", ""]) {
      localStorage.setItem("inventario.bodega.pedro", raw);
      expect(rememberedWarehouse("pedro")).toBeNull();
    }
  });

  it("sin almacenamiento local no falla: solo no recuerda", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("bloqueado"); });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("bloqueado"); });
    expect(() => rememberWarehouse("pedro", 2)).not.toThrow();
    expect(rememberedWarehouse("pedro")).toBeNull();
  });
});
