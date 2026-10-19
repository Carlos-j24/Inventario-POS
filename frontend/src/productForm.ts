// Formulario de producto (spec 006, T2), sin React para poder probarlo. Solo se envía lo que cambió:
// así quien no tiene permiso de precios puede guardar el resto sin que el servidor responda 403.
import type { AdminProduct } from "./api";
import { centsToApi, toCents } from "./money";

export interface ProductForm {
  sku: string;
  name: string;
  category: string;
  base_unit: string;
  barcode: string;
  /** Lo que escribe el usuario: "12500", "12.500,50"… */
  price: string;
  tax_rate: "0" | "5" | "19";
  vat_excluded: boolean;
  allows_fractions: boolean;
  min_stock: string;
  is_active: boolean;
}

export const EMPTY_FORM: ProductForm = {
  sku: "", name: "", category: "", base_unit: "und", barcode: "", price: "", tax_rate: "19",
  vat_excluded: false, allows_fractions: false, min_stock: "0", is_active: true,
};

/** Precio escrito en formato colombiano ("12.500,50") o con punto decimal ("12500.5") a centavos. */
export function priceToCents(text: string): number | null {
  const clean = text.trim().replace(/\s|\$/g, "");
  if (!clean) return null;
  // Con coma, la coma es el decimal y los puntos son miles; sin coma, un solo punto con 1–2 decimales es decimal.
  const normalized = clean.includes(",")
    ? clean.replace(/\./g, "").replace(",", ".")
    : /^\d+\.\d{1,2}$/.test(clean) ? clean : clean.replace(/\./g, "");
  if (!/^\d+(\.\d{1,2})?$/.test(normalized)) return null;
  return toCents(normalized);
}

export function toForm(p: AdminProduct): ProductForm {
  return {
    sku: p.sku, name: p.name, category: String(p.category), base_unit: p.base_unit, barcode: p.barcode ?? "",
    price: p.price_pending ? "" : String(toCents(p.sale_price) / 100), tax_rate: p.tax_rate, vat_excluded: p.vat_excluded,
    allows_fractions: p.allows_fractions, min_stock: String(Number(p.min_stock)), is_active: p.is_active,
  };
}

/**
 * Cuerpo para la API. Nuevo: todo (sin precio ni IVA si no hay permiso). Edición: solo lo que
 * cambió respecto al original. Devuelve un error legible si algo no se puede enviar.
 */
export function productPayload(form: ProductForm, original: AdminProduct | null, canPrice: boolean): { body: Record<string, unknown> } | { error: string } {
  const cents = priceToCents(form.price);
  if (canPrice && form.price.trim() && cents == null) return { error: "Escribe el precio como 12500 o 12.500,50." };
  if (canPrice && !original && cents == null) return { error: "Escribe el precio de venta." };
  if (form.vat_excluded && form.tax_rate !== "0") return { error: "Un producto excluido de IVA debe tener tarifa 0 %." };

  const all: Record<string, unknown> = {
    sku: form.sku.trim(), name: form.name.trim(), category: Number(form.category), base_unit: form.base_unit,
    barcode: form.barcode.trim() || null, allows_fractions: form.allows_fractions, min_stock: form.min_stock || "0",
    is_active: form.is_active,
  };
  if (canPrice) {
    if (cents != null) all.sale_price = centsToApi(cents);
    all.tax_rate = form.tax_rate;
    all.vat_excluded = form.vat_excluded;
  }
  if (!original) return { body: all };

  const before: Record<string, unknown> = {
    sku: original.sku, name: original.name, category: original.category, base_unit: original.base_unit,
    barcode: original.barcode || null, allows_fractions: original.allows_fractions,
    min_stock: String(Number(original.min_stock)), is_active: original.is_active,
    tax_rate: original.tax_rate, vat_excluded: original.vat_excluded,
    sale_price: original.price_pending ? null : original.sale_price,
  };
  const body: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(all)) {
    const changed = key === "min_stock" ? Number(value) !== Number(before[key]) : value !== before[key];
    if (changed) body[key] = value; // sin permiso, precio e IVA ni siquiera están en `all`
  }
  return { body };
}
