import { describe, expect, it } from "vitest";

import type { Product } from "./api";
import { offlineTicket, splitTax } from "./ticket";

const product = (over: Partial<Product>): Product => ({
  id: 1, sku: "X", name: "X", category: "", base_unit: "und", barcode: null, sale_price: "0", tax_rate: "19",
  allows_fractions: false, min_stock: "0", units: [], ...over,
});
const hammer = product({ id: 2, name: "Martillo 16 oz", sale_price: "28000.00" });
const cable = product({ id: 1, name: "Cable THHN", base_unit: "m", sale_price: "3200.00", allows_fractions: true });
const seed = product({ id: 3, name: "Semillas", sale_price: "5000.00", tax_rate: "0", vat_excluded: true });

describe("splitTax", () => {
  it("separa el IVA como el servidor", () => {
    expect(splitTax(3200000, 19)).toEqual({ base: 2689076, tax: 510924 }); // 26.890,76 + 5.109,24
    expect(splitTax(5600000, 19)).toEqual({ base: 4705882, tax: 894118 });
    expect(splitTax(500000, 0)).toEqual({ base: 500000, tax: 0 });
  });
});

describe("offlineTicket", () => {
  const base = {
    business: { name: "Ferretería", trade_name: "", nit: "800197268-4", address: "", city: "", phone: "", email: "", tax_regime: "" },
    lines: [
      { key: "a", product: hammer, unit: "und", quantity: 2 },
      { key: "b", product: cable, unit: "m", quantity: 10 },
      { key: "c", product: seed, unit: "und", quantity: 1 },
    ],
    payments: [{ method: "CASH" as const, amountCents: 10000000 }, { method: "CARD" as const, amountCents: 1000000 }],
    changeCents: 1700000,
    cashier: "maria",
    register: "CAJA2",
    now: new Date("2026-10-17T17:00:00Z"),
  };

  it("contingencia: código, totales e IVA por tarifa", () => {
    const t = offlineTicket({ ...base, contingencyCode: "CT21" });
    expect([t.title, t.code]).toEqual(["Documento de contingencia", "CT21"]);
    expect(t.total).toBe("93000.00");
    expect(t.taxes).toEqual([
      { rate: "19", base: "73949.58", tax: "14050.42" },
      { rate: "excluido", base: "5000.00", tax: "0.00" },
    ]);
    expect((Number(t.subtotal) + Number(t.tax)).toFixed(2)).toBe(t.total);
    expect(t.lines[1]).toEqual({ name: "Cable THHN", quantity: "10", unit: "m", unit_price: "3200.00", total: "32000.00" });
    expect(t.payments).toEqual([{ label: "Efectivo", amount: "100000.00" }, { label: "Tarjeta", amount: "10000.00" }]);
    expect(t.change).toBe("17000.00");
    expect([t.register, t.cashier, t.issued_at]).toEqual(["CAJA2", "maria", "2026-10-17T17:00:00.000Z"]);
    expect(t.notes[0]).toMatch(/contingencia/);
    expect([t.qr_svg, t.cude, t.status, t.customer]).toEqual([null, null, null, null]);
  });

  it("sin bloque de contingencia lo dice", () => {
    const t = offlineTicket({ ...base, contingencyCode: null });
    expect([t.title, t.code]).toEqual(["Comprobante de venta sin conexión", null]);
    expect(t.notes[0]).toMatch(/se genera al volver la conexión/);
  });
});
