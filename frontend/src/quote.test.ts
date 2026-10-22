import { describe, expect, it } from "vitest";

import type { Customer, Product, QuoteLine } from "./api";
import type { CartLine } from "./cart";
import { convertBody, defaultPicks, parseQuantity, plainQuantity, quoteBody } from "./quote";

const cable: Product = {
  id: 1, sku: "CAB-12", name: "Cable THHN", category: "Eléctricos", base_unit: "m", barcode: null,
  sale_price: "3200.00", tax_rate: "19", allows_fractions: true, min_stock: "0", units: [{ unit: "rollo", factor: "100", barcode: null }],
};
const hammer: Product = { ...cable, id: 2, sku: "MAR-16", name: "Martillo", base_unit: "und", allows_fractions: false, units: [] };
const cart = (product: Product, quantity: number, unit = product.base_unit): CartLine => ({ key: product.sku + unit, product, unit, quantity });
const builder = { id: 7, name: "Constructora" } as Customer;

const form = (over: Partial<Parameters<typeof quoteBody>[0]> = {}) => ({
  clientUuid: "u-1", customer: null, customerName: " Don Jorge ", customerPhone: " 300 ", note: " Obra ", validDays: "8",
  lines: [cart(cable, 1.5, "rollo"), cart(hammer, 2)], ...over,
});

describe("quoteBody", () => {
  it("arma el cuerpo con el cliente escrito, la vigencia y las líneas", () => {
    expect(quoteBody(form())).toEqual({
      body: {
        client_uuid: "u-1", customer: null, customer_name: "Don Jorge", customer_phone: "300", note: "Obra", valid_days: 8,
        lines: [{ product: 1, unit: "rollo", quantity: "1.5" }, { product: 2, unit: "und", quantity: "2" }],
      },
    });
  });

  it("basta un cliente registrado", () => {
    const result = quoteBody(form({ customerName: "", customer: builder, validDays: "30" }));
    expect("body" in result && result.body).toMatchObject({ customer: 7, customer_name: "", valid_days: 30 });
  });

  it.each([
    [{ customerName: "  " }, "Escribe a nombre de quién va"],
    [{ validDays: "0" }, "La vigencia va de 1 a 30 días"],
    [{ validDays: "31" }, "La vigencia va de 1 a 30 días"],
    [{ validDays: "2.5" }, "La vigencia va de 1 a 30 días"],
    [{ validDays: "" }, "La vigencia va de 1 a 30 días"],
    [{ lines: [] }, "Agrega al menos un producto"],
    [{ lines: [cart(hammer, 1.5)] }, "MAR-16: "],
    [{ lines: [cart(cable, 0)] }, "CAB-12: La cantidad debe ser mayor que cero"],
  ])("%j → error", (over, message) => {
    const result = quoteBody(form(over));
    expect("error" in result && result.error).toContain(message);
  });
});

const line = (over: Partial<QuoteLine>): QuoteLine => ({
  id: 1, product: 1, sku: "MAR-16", name: "Martillo", unit: "und", quantity: "10.000", unit_price: "28000.00", tax_rate: "19",
  vat_excluded: false, total: "280000.00", subtotal: "0", tax: "0", active: true, in_orders: "4.000", charged: "0.000", remaining: "6.000", ...over,
});
const rolls = line({ id: 2, sku: "CAB-12", name: "Cable", unit: "rollo", quantity: "2.000", in_orders: "0.000", remaining: "2.000" });

describe("convertir", () => {
  it("precarga lo que queda de cada línea que sigue a la venta", () => {
    expect(defaultPicks([line({}), rolls, line({ id: 3, active: false })])).toEqual({ 1: "6", 2: "2", 3: "0" });
  });

  it("manda solo lo que se lleva, con coma o punto", () => {
    expect(convertBody("u-2", [line({}), rolls], { 1: "2,5", 2: "0" })).toEqual({
      body: { client_uuid: "u-2", lines: [{ quote_line: 1, quantity: "2.5" }] },
    });
    expect(convertBody("u-2", [line({}), rolls], { 1: "6", 2: "2" })).toEqual({
      body: { client_uuid: "u-2", lines: [{ quote_line: 1, quantity: "6" }, { quote_line: 2, quantity: "2" }] },
    });
  });

  it.each([
    [{ 1: "7", 2: "0" }, "MAR-16: quedan 6 und por convertir"],
    [{ 1: "x", 2: "0" }, "MAR-16: escribe la cantidad"],
    [{ 1: "0", 2: "0" }, "Escribe cuánto se lleva el cliente"],
    [{ 1: "0" }, "Escribe cuánto se lleva el cliente"],
  ])("%j → error", (picks, message) => {
    const result = convertBody("u", [line({}), rolls], picks);
    expect("error" in result && result.error).toContain(message);
  });

  it("no deja convertir lo que ya no está a la venta", () => {
    const result = convertBody("u", [line({ active: false })], { 1: "1" });
    expect("error" in result && result.error).toBe("MAR-16 ya no está a la venta: déjalo en 0.");
  });
});

describe("cantidades", () => {
  it.each([["3", 3], ["2,5", 2.5], [" 0.25 ", 0.25], ["0", 0]])("%j → %s", (text, value) => expect(parseQuantity(text)).toBe(value));
  it.each(["", "-1", "abc", "1,2,3"])("%j no es cantidad", (text) => expect(parseQuantity(text)).toBeNull());
  it("quita los ceros de sobra", () => {
    expect([plainQuantity("12.500"), plainQuantity("6.000"), plainQuantity("0.000")]).toEqual(["12.5", "6", "0"]);
  });
});
