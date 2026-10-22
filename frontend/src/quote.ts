// Cotizaciones (spec 007, T4), sin React para poder probarlo. Las reglas son las del servidor
// (sales/quotes.py); aquí se avisan antes de enviar.
import type { Customer, QuoteLine } from "./api";
import { quantityError, type CartLine } from "./cart";

export const DEFAULT_VALID_DAYS = 8;
export const MAX_VALID_DAYS = 30;

/** Cantidad escrita con coma o punto; null si no es un número mayor o igual a cero. */
export function parseQuantity(text: string): number | null {
  const clean = text.trim().replace(",", ".");
  if (!/^\d+(\.\d+)?$/.test(clean)) return null;
  return Number(clean);
}

/** "12.500" → "12.5": para mostrar y para precargar lo que queda por convertir. */
export function plainQuantity(value: string): string {
  return String(Number(value));
}

export function quoteBody(form: {
  clientUuid: string;
  customer: Customer | null;
  customerName: string;
  customerPhone: string;
  note: string;
  validDays: string;
  lines: CartLine[];
}): { body: Record<string, unknown> } | { error: string } {
  if (!form.customerName.trim() && !form.customer) return { error: "Escribe a nombre de quién va la cotización o elige un cliente." };
  const days = Number(form.validDays);
  if (!Number.isInteger(days) || days < 1 || days > MAX_VALID_DAYS) return { error: `La vigencia va de 1 a ${MAX_VALID_DAYS} días.` };
  if (form.lines.length === 0) return { error: "Agrega al menos un producto." };
  for (const line of form.lines) {
    const problem = quantityError(line);
    if (problem) return { error: `${line.product.sku}: ${problem}` };
  }
  return {
    body: {
      client_uuid: form.clientUuid,
      customer: form.customer?.id ?? null,
      customer_name: form.customerName.trim(),
      customer_phone: form.customerPhone.trim(),
      note: form.note.trim(),
      valid_days: days,
      lines: form.lines.map((l) => ({ product: l.product.id, unit: l.unit, quantity: String(l.quantity) })),
    },
  };
}

/** Lo que se precarga para convertir: todo lo que queda de cada línea que sigue a la venta. */
export function defaultPicks(lines: QuoteLine[]): Record<number, string> {
  return Object.fromEntries(lines.map((l) => [l.id, l.active ? plainQuantity(l.remaining) : "0"]));
}

/** Las líneas a convertir (las que llevan algo); valida contra lo que queda por convertir. */
export function convertBody(clientUuid: string, lines: QuoteLine[], picks: Record<number, string>):
  { body: Record<string, unknown> } | { error: string } {
  const chosen = [];
  for (const line of lines) {
    const quantity = parseQuantity(picks[line.id] ?? "0");
    if (quantity === null) return { error: `${line.sku}: escribe la cantidad (0 si no se lleva).` };
    if (quantity === 0) continue;
    if (!line.active) return { error: `${line.sku} ya no está a la venta: déjalo en 0.` };
    if (quantity > Number(line.remaining)) return { error: `${line.sku}: quedan ${plainQuantity(line.remaining)} ${line.unit} por convertir.` };
    chosen.push({ quote_line: line.id, quantity: String(quantity) });
  }
  if (chosen.length === 0) return { error: "Escribe cuánto se lleva el cliente de al menos un producto." };
  return { body: { client_uuid: clientUuid, lines: chosen } };
}
