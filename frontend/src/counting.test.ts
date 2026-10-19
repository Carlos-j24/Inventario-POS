import { describe, expect, it } from "vitest";

import type { CountLine } from "./api";
import { filterLines, findLine, parseCount } from "./counting";

const line = (over: Partial<CountLine>): CountLine => ({
  id: 1, product: 1, sku: "X", name: "X", barcode: null, base_unit: "und", units: [], counted: null, counted_at: null,
  counted_by: null, marked_zero: false, expected: null, difference: null, value: null, ...over,
});
const hammer = line({ id: 1, sku: "MAR-16", name: "Martillo 16 oz", barcode: "770MAR" });
const cable = line({ id: 2, sku: "CAB-12", name: "Cable THHN calibre 12", base_unit: "m", units: [{ unit: "rollo", factor: "100", barcode: "770ROLLO" }], counted: "50.000" });
const lines = [hammer, cable];

describe("findLine", () => {
  it("por código de barras del producto, de una presentación o por SKU", () => {
    expect(findLine(lines, "770MAR")).toEqual({ line: hammer, unit: "und" });
    expect(findLine(lines, " 770rollo ")).toEqual({ line: cable, unit: "rollo" }); // el rollo se cuenta en rollos
    expect(findLine(lines, "cab-12")).toEqual({ line: cable, unit: "m" });
  });

  it("nada si no está o está vacío", () => {
    expect(findLine(lines, "999")).toBeNull();
    expect(findLine(lines, "  ")).toBeNull();
    expect(findLine(lines, "martillo")).toBeNull(); // el nombre no: eso es para el filtro
    expect(findLine([line({ barcode: "", units: [{ unit: "caja", factor: "10", barcode: "" }] })], "  ")).toBeNull(); // código vacío
  });
});

describe("filterLines", () => {
  it("filtra por palabras del SKU o el nombre", () => {
    expect(filterLines(lines, "", false)).toEqual(lines);
    expect(filterLines(lines, "cable 12", false)).toEqual([cable]);
    expect(filterLines(lines, "mar-16", false)).toEqual([hammer]);
    expect(filterLines(lines, "tornillo", false)).toEqual([]);
    expect(filterLines(lines, "cable 16", false)).toEqual([]); // todas las palabras, no alguna
  });

  it("solo los que faltan por contar", () => {
    expect(filterLines(lines, "", true)).toEqual([hammer]);
    expect(filterLines(lines, "cable", true)).toEqual([]);
  });
});

describe("parseCount", () => {
  it.each([["0", "0"], ["12", "12"], ["12,5", "12.5"], [" 3.25 ", "3.25"]])("%j → %s", (text, value) => {
    expect(parseCount(text)).toBe(value);
  });

  it.each(["", "-1", "abc", "1,2,3", "1.2.3"])("%j no es una cantidad", (text) => {
    expect(parseCount(text)).toBeNull();
  });
});
