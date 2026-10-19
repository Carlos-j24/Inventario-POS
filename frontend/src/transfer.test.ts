import { describe, expect, it } from "vitest";

import type { Product } from "./api";
import { newTransferLine, transferBody } from "./transfer";

const cable: Product = {
  id: 1, sku: "CAB-12", name: "Cable THHN", category: "Eléctricos", base_unit: "m", barcode: null,
  sale_price: "3200.00", tax_rate: "19", allows_fractions: true, min_stock: "0", units: [{ unit: "rollo", factor: "100", barcode: null }],
};
const form = (over: Partial<Parameters<typeof transferBody>[0]> = {}) => ({
  clientUuid: "u-1", origin: 1, destination: 2, note: "  Para la vitrina ", lines: [{ ...newTransferLine(cable, "rollo"), quantity: "1,5" }], ...over,
});

describe("transferBody", () => {
  it("arma el cuerpo con la cantidad en la unidad elegida", () => {
    expect(transferBody(form())).toEqual({
      body: { client_uuid: "u-1", origin: 1, destination: 2, note: "Para la vitrina", lines: [{ product: 1, unit: "rollo", quantity: "1.5" }] },
    });
  });

  it.each([
    [{ origin: null }, "Elige de qué bodega sale"],
    [{ destination: null }, "Elige de qué bodega sale"],
    [{ destination: 1 }, "bodegas distintas"],
    [{ lines: [] }, "Agrega al menos un producto"],
    [{ lines: [{ ...newTransferLine(cable, "m"), quantity: "0" }] }, "CAB-12: la cantidad debe ser mayor que cero"],
    [{ lines: [{ ...newTransferLine(cable, "m"), quantity: "abc" }] }, "mayor que cero"],
  ])("%j → error", (over, message) => {
    const result = transferBody(form(over));
    expect("error" in result && result.error).toContain(message);
  });

  it("una línea nueva empieza en 1 con su propia clave", () => {
    const a = newTransferLine(cable, "m");
    expect({ unit: a.unit, quantity: a.quantity }).toEqual({ unit: "m", quantity: "1" });
    expect(a.key).not.toBe(newTransferLine(cable, "m").key);
  });
});
