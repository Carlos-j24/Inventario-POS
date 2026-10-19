// Traslado entre bodegas (spec 006, T7), sin React para poder probarlo. Las reglas son las del
// servidor (inventory/transfers.py); aquí se avisan antes de enviar.
import type { Product } from "./api";

export interface TransferDraftLine {
  key: string;
  product: Product;
  unit: string;
  quantity: string;
}

export function newTransferLine(product: Product, unit: string): TransferDraftLine {
  return { key: crypto.randomUUID(), product, unit, quantity: "1" };
}

export function transferBody(form: { clientUuid: string; origin: number | null; destination: number | null; note: string; lines: TransferDraftLine[] }):
  { body: Record<string, unknown> } | { error: string } {
  if (!form.origin || !form.destination) return { error: "Elige de qué bodega sale y a cuál entra." };
  if (form.origin === form.destination) return { error: "El origen y el destino deben ser bodegas distintas." };
  if (form.lines.length === 0) return { error: "Agrega al menos un producto." };
  const lines = [];
  for (const line of form.lines) {
    const quantity = Number(line.quantity.replace(",", "."));
    if (!(quantity > 0)) return { error: `${line.product.sku}: la cantidad debe ser mayor que cero.` };
    lines.push({ product: line.product.id, unit: line.unit, quantity: String(quantity) });
  }
  return { body: { client_uuid: form.clientUuid, origin: form.origin, destination: form.destination, note: form.note.trim(), lines } };
}
