import { describe, expect, it } from "vitest";

import type { Product } from "./api";
import {
  cartTotalCents, checkPayments, findByCode, lineTotalCents, quantityError, searchProducts, unitPriceCents,
  type CartLine,
} from "./cart";

const cable: Product = {
  id: 1, sku: "CAB-12", name: "Cable THHN calibre 12", category: "Eléctricos", base_unit: "m",
  barcode: "7701", sale_price: "3200.00", tax_rate: "19", allows_fractions: true, min_stock: "50",
  units: [{ unit: "rollo", factor: "100.000", barcode: "7702" }],
};
const hammer: Product = {
  id: 2, sku: "MAR-16", name: "Martillo 16 oz", category: "Herramientas", base_unit: "und",
  barcode: null, sale_price: "28000.00", tax_rate: "19", allows_fractions: false, min_stock: "5", units: [],
};
const line = (product: Product, quantity: number, unit = product.base_unit): CartLine => ({
  key: "k", product, unit, quantity,
});

describe("precios del carrito", () => {
  it("multiplica el precio base por el factor de la presentación", () => {
    expect(unitPriceCents(cable, "m")).toBe(320000);
    expect(unitPriceCents(cable, "rollo")).toBe(32000000);
  });

  it("suma líneas fraccionadas igual que el backend", () => {
    // Mismos valores que calculó el servidor para la venta V-000001 de la demo.
    expect(lineTotalCents(line(cable, 15.5))).toBe(4960000);
    expect(cartTotalCents([line(cable, 15.5), line(hammer, 1)])).toBe(7760000);
  });
});

describe("cantidades", () => {
  it("rechaza fracciones en productos que no se fraccionan", () => {
    expect(quantityError(line(hammer, 0.5))).toMatch(/no se vende fraccionado/);
    expect(quantityError(line(hammer, 2))).toBeNull();
    expect(quantityError(line(cable, 2.5))).toBeNull();
  });

  it("rechaza cero y negativos", () => {
    expect(quantityError(line(cable, 0))).not.toBeNull();
    expect(quantityError(line(cable, -1))).not.toBeNull();
  });
});

describe("búsqueda", () => {
  it("encuentra por código de barras del producto o de la presentación, y por SKU", () => {
    expect(findByCode([cable, hammer], "7701")).toEqual({ product: cable, unit: "m" });
    expect(findByCode([cable, hammer], "7702")).toEqual({ product: cable, unit: "rollo" });
    expect(findByCode([cable, hammer], "mar-16")).toEqual({ product: hammer, unit: "und" });
    expect(findByCode([cable, hammer], "nada")).toBeNull();
  });

  it("busca por todas las palabras, en cualquier orden", () => {
    expect(searchProducts([cable, hammer], "12 cable")).toEqual([cable]);
    expect(searchProducts([cable, hammer], "")).toEqual([]);
  });
});

describe("cobro", () => {
  const total = 8400000; // 84.000

  it("calcula las vueltas del efectivo", () => {
    const r = checkPayments(total, [{ method: "CASH", amountCents: 10000000 }]);
    expect(r.error).toBeNull();
    expect(r.changeCents).toBe(1600000);
  });

  it("acepta pago mixto con vueltas solo del efectivo", () => {
    const r = checkPayments(total, [
      { method: "CARD", amountCents: 6000000 },
      { method: "CASH", amountCents: 3000000 },
    ]);
    expect(r.error).toBeNull();
    expect(r.changeCents).toBe(600000);
  });

  it("avisa cuánto falta", () => {
    const r = checkPayments(total, [{ method: "CASH", amountCents: 5000000 }]);
    expect(r.error).not.toBeNull();
    expect(r.missingCents).toBe(3400000);
  });

  it("no deja que tarjeta o transferencia pasen del total ni que sobre efectivo", () => {
    expect(checkPayments(total, [{ method: "CARD", amountCents: 9000000 }]).error).not.toBeNull();
    expect(
      checkPayments(total, [{ method: "TRANSFER", amountCents: total }, { method: "CASH", amountCents: 100 }]).error,
    ).not.toBeNull();
    expect(checkPayments(total, []).error).not.toBeNull();
  });
});
