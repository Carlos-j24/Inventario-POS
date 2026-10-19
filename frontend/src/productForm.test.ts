import { describe, expect, it } from "vitest";

import type { AdminProduct } from "./api";
import { EMPTY_FORM, priceToCents, productPayload, toForm } from "./productForm";

const hammer: AdminProduct = {
  id: 2, sku: "MAR-16", name: "Martillo 16 oz", category: 3, category_name: "Herramientas", base_unit: "und",
  barcode: null, sale_price: "28000.00", tax_rate: "19", vat_excluded: false, allows_fractions: false,
  min_stock: "5.000", is_active: true, price_pending: false, has_movements: true, units: [],
};

describe("priceToCents", () => {
  it.each([
    ["12500", 1250000], ["12.500", 1250000], ["1.250.000", 125000000], ["12.500,50", 1250050],
    ["3199.99", 319999], ["3199,9", 319990], ["$ 28.000", 2800000], ["0", 0],
  ])("%s → %i centavos", (text, cents) => {
    expect(priceToCents(text)).toBe(cents);
  });

  it.each(["", "  ", "abc", "12,5,0", "-100", "1.2.3,456"])("%j no es un precio", (text) => {
    expect(priceToCents(text)).toBeNull();
  });
});

describe("productPayload", () => {
  it("nuevo con permiso de precios: todo, con el precio en formato de la API", () => {
    const form = { ...EMPTY_FORM, sku: " DES-PH2 ", name: "Destornillador", category: "3", price: "12.500", barcode: "  " };
    expect(productPayload(form, null, true)).toEqual({ body: {
      sku: "DES-PH2", name: "Destornillador", category: 3, base_unit: "und", barcode: null, allows_fractions: false,
      min_stock: "0", is_active: true, sale_price: "12500.00", tax_rate: "19", vat_excluded: false,
    } });
  });

  it("nuevo sin permiso de precios: sin precio ni IVA", () => {
    const result = productPayload({ ...EMPTY_FORM, sku: "X", name: "X", category: "1", price: "999" }, null, false);
    expect("body" in result && Object.keys(result.body)).not.toContain("sale_price");
    expect("body" in result && Object.keys(result.body)).not.toContain("tax_rate");
  });

  it("errores antes de llamar a la API", () => {
    expect(productPayload({ ...EMPTY_FORM, category: "1" }, null, true)).toEqual({ error: "Escribe el precio de venta." });
    expect(productPayload({ ...EMPTY_FORM, price: "doce" }, null, true)).toEqual({ error: "Escribe el precio como 12500 o 12.500,50." });
    expect(productPayload({ ...EMPTY_FORM, price: "1000", vat_excluded: true }, null, true)).toEqual({ error: "Un producto excluido de IVA debe tener tarifa 0 %." });
  });

  it("edición: solo lo que cambió", () => {
    const form = toForm(hammer);
    expect(form.price).toBe("28000");
    expect(productPayload(form, hammer, true)).toEqual({ body: {} });
    expect(productPayload({ ...form, name: "Martillo 20 oz", min_stock: "5" }, hammer, true)).toEqual({ body: { name: "Martillo 20 oz" } });
    expect(productPayload({ ...form, price: "28.000" }, hammer, true)).toEqual({ body: {} }); // mismo precio escrito distinto
    expect(productPayload({ ...form, price: "29500", min_stock: "4" }, hammer, true)).toEqual({ body: { sale_price: "29500.00", min_stock: "4" } });
    expect(productPayload({ ...form, barcode: "770123" }, hammer, true)).toEqual({ body: { barcode: "770123" } });
    expect(productPayload({ ...form, min_stock: "5.00" }, hammer, true)).toEqual({ body: {} }); // el mismo número
  });

  it("edición sin permiso de precios: nunca manda precio ni IVA, aunque el formulario cambie", () => {
    const form = { ...toForm(hammer), price: "1", tax_rate: "0" as const, name: "Nuevo nombre" };
    expect(productPayload(form, hammer, false)).toEqual({ body: { name: "Nuevo nombre" } });
  });

  it("producto pendiente de precio: el precio va aunque sea el primero", () => {
    const pending = { ...hammer, sale_price: "0.00", price_pending: true, is_active: false };
    const form = toForm(pending);
    expect(form.price).toBe("");
    expect(productPayload({ ...form, price: "15000" }, pending, true)).toEqual({ body: { sale_price: "15000.00" } });
    expect(productPayload({ ...form, price: "0" }, pending, true)).toEqual({ body: { sale_price: "0.00" } });
  });
});
