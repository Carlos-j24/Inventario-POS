// Lógica del carrito del POS, sin React para poder probarla aparte.
// El backend recalcula y es la fuente de verdad; esto es lo que ve el cajero mientras cobra.
import type { Order, PaymentMethod, Product } from "./api";
import { toCents } from "./money";

export interface CartLine {
  key: string;
  product: Product;
  unit: string; // código de la unidad vendida (base o presentación)
  quantity: number;
  /** Línea que viene de un pedido (spec 002): precio acordado y tope de lo pedido; la unidad no cambia. */
  order?: { lineId: number; max: number; priceCents: number };
}

export function unitFactor(product: Product, unit: string): number {
  if (unit === product.base_unit) return 1;
  const found = product.units.find((u) => u.unit === unit);
  if (!found) throw new Error(`${product.sku} no se maneja en '${unit}'.`);
  return Number(found.factor);
}

/** Precio en centavos por unidad vendida: precio base × factor, como en el backend. */
export function unitPriceCents(product: Product, unit: string): number {
  return Math.round(toCents(product.sale_price) * unitFactor(product, unit));
}

/** Precio de la línea: el acordado en el pedido o, si no viene de uno, el del catálogo. */
export function linePriceCents(line: CartLine): number {
  return line.order ? line.order.priceCents : unitPriceCents(line.product, line.unit);
}

export function lineTotalCents(line: CartLine): number {
  return Math.round(linePriceCents(line) * line.quantity);
}

export function cartTotalCents(lines: CartLine[]): number {
  return lines.reduce((sum, line) => sum + lineTotalCents(line), 0);
}

/** Una cantidad es válida si es positiva y, si el producto no se fracciona, entera en unidad base. */
export function quantityError(line: CartLine): string | null {
  if (!(line.quantity > 0)) return "La cantidad debe ser mayor que cero.";
  if (line.order && line.quantity > line.order.max) return `Se pidieron ${line.order.max}: no se puede cobrar más.`;
  const base = line.quantity * unitFactor(line.product, line.unit);
  if (!line.product.allows_fractions && Math.abs(base - Math.round(base)) > 1e-9) {
    return `${line.product.name} no se vende fraccionado.`;
  }
  return null;
}

/** Busca por código de barras (del producto o de una presentación) o por SKU exacto. */
export function findByCode(products: Product[], code: string): { product: Product; unit: string } | null {
  const c = code.trim().toLowerCase();
  if (!c) return null;
  for (const product of products) {
    if (product.barcode?.toLowerCase() === c || product.sku.toLowerCase() === c) {
      return { product, unit: product.base_unit };
    }
    const pres = product.units.find((u) => u.barcode?.toLowerCase() === c);
    if (pres) return { product, unit: pres.unit };
  }
  return null;
}

export function searchProducts(products: Product[], text: string, limit = 8): Product[] {
  const words = text.trim().toLowerCase().split(/\s+/).filter(Boolean);
  if (!words.length) return [];
  return products
    .filter((p) => {
      const haystack = `${p.sku} ${p.name} ${p.category}`.toLowerCase();
      return words.every((w) => haystack.includes(w));
    })
    .slice(0, limit);
}

export interface PaymentDraft {
  method: PaymentMethod;
  amountCents: number;
}

/** Reglas de cobro del backend (cash.services.apply_payments), para avisar antes de enviar. */
export function checkPayments(totalCents: number, payments: PaymentDraft[]) {
  const used = payments.filter((p) => p.amountCents > 0);
  const nonCash = used.filter((p) => p.method !== "CASH").reduce((s, p) => s + p.amountCents, 0);
  const cash = used.filter((p) => p.method === "CASH").reduce((s, p) => s + p.amountCents, 0);
  const cashDue = totalCents - nonCash;
  let error: string | null = null;
  if (!used.length) error = "Registra al menos un pago.";
  else if (nonCash > totalCents) error = "Tarjeta y transferencia no pueden superar el total.";
  else if (cashDue === 0 && cash > 0) error = "La venta ya está cubierta: sobra el efectivo.";
  else if (cash < cashDue) error = "Falta dinero para cubrir el total.";
  return {
    error,
    missingCents: Math.max(0, cashDue - cash),
    changeCents: error ? 0 : cash - cashDue,
    payments: used,
  };
}

/** Agrega un producto al carrito: si ya está en esa unidad, suma 1; si no, una línea nueva. */
export function addToCart(lines: CartLine[], product: Product, unit = product.base_unit): CartLine[] {
  const same = lines.find((l) => l.product.id === product.id && l.unit === unit);
  if (same) return lines.map((l) => (l === same ? { ...l, quantity: l.quantity + 1 } : l));
  return [...lines, { key: crypto.randomUUID(), product, unit, quantity: 1 }];
}

/**
 * Convierte un pedido en líneas de carrito con su precio acordado y su tope.
 * Necesita el catálogo para saber si cada producto se fracciona y sus presentaciones.
 */
export function orderToCart(order: Order, products: Product[]): CartLine[] {
  return order.lines.map((ol) => {
    const product = products.find((p) => p.id === ol.product);
    if (!product) throw new Error(`${ol.sku} no está en el catálogo de esta caja: actualiza la página.`);
    return {
      key: `order-${ol.id}`,
      product,
      unit: ol.unit,
      quantity: Number(ol.quantity),
      order: { lineId: ol.id, max: Number(ol.quantity), priceCents: toCents(ol.unit_price) },
    };
  });
}
