import { describe, expect, it } from "vitest";

import { adjustmentBody, directionFor, newLine, REASONS, type DraftLine } from "./adjustment";
import type { Product } from "./api";

const cable: Product = {
  id: 1, sku: "CAB-12", name: "Cable THHN", category: "", base_unit: "m", barcode: null, sale_price: "3200.00",
  tax_rate: "19", allows_fractions: true, min_stock: "50", units: [{ unit: "rollo", factor: "100", barcode: null }],
};
const line = (over: Partial<DraftLine> = {}): DraftLine => ({ key: "a", product: cable, unit: "m", quantity: "2", direction: "OUT", cost: "", ...over });
const base = { clientUuid: "u-1", warehouse: 1, reason: "DAMAGE", note: "Se mojó", lines: [line()] };

describe("motivos y sentido", () => {
  it("no se ofrece conteo físico", () => {
    expect(REASONS.map((r) => r.id)).not.toContain("PHYSICAL_COUNT");
  });

  it("el motivo manda el sentido, salvo error de registro", () => {
    expect(directionFor("DAMAGE", "IN")).toBe("OUT");
    expect(directionFor("LOSS", "IN")).toBe("OUT");
    expect(directionFor("SURPLUS", "OUT")).toBe("IN");
    expect(directionFor("RECORD_ERROR", "IN")).toBe("IN");
    expect(directionFor("RECORD_ERROR", "OUT")).toBe("OUT");
  });

  it("una línea nueva toma el sentido del motivo", () => {
    expect(newLine(cable, "rollo", "SURPLUS")).toMatchObject({ product: cable, unit: "rollo", quantity: "1", direction: "IN", cost: "" });
    expect(newLine(cable, "m", "DAMAGE").direction).toBe("OUT");
  });
});

describe("adjustmentBody", () => {
  it("arma el cuerpo de la API", () => {
    expect(adjustmentBody({ ...base, note: "  Se mojó  ", lines: [line({ quantity: "2,5" })] })).toEqual({ body: {
      client_uuid: "u-1", warehouse: 1, reason: "DAMAGE", note: "Se mojó",
      lines: [{ product: 1, unit: "m", quantity: "2.5", direction: "OUT" }],
    } });
  });

  it("el sentido sale del motivo aunque la línea diga otra cosa", () => {
    const result = adjustmentBody({ ...base, reason: "SURPLUS", lines: [line({ direction: "OUT", cost: "250.000" , unit: "rollo" })] });
    expect("body" in result && (result.body.lines as unknown[])[0]).toEqual({ product: 1, unit: "rollo", quantity: "2", direction: "IN", unit_cost: "250000.00" });
  });

  it("el costo solo va en las entradas", () => {
    const result = adjustmentBody({ ...base, lines: [line({ cost: "9000" })] });
    expect("body" in result && (result.body.lines as Record<string, unknown>[])[0]).not.toHaveProperty("unit_cost");
  });

  it.each([
    [{ warehouse: null }, "Elige la bodega."],
    [{ reason: "PHYSICAL_COUNT" }, "Elige el motivo."],
    [{ note: "   " }, "Escribe una nota: qué pasó con la mercancía."],
    [{ lines: [] }, "Agrega al menos un producto."],
    [{ lines: [line({ quantity: "0" })] }, "CAB-12: la cantidad debe ser mayor que cero."],
    [{ lines: [line({ quantity: "dos" })] }, "CAB-12: la cantidad debe ser mayor que cero."],
    [{ reason: "SURPLUS", lines: [line({ cost: "barato" })] }, "CAB-12: escribe el costo como 12500 o 12.500,50."],
  ])("%j → %s", (over, error) => {
    expect(adjustmentBody({ ...base, ...over })).toEqual({ error });
  });
});
