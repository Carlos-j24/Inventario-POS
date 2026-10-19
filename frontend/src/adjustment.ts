// Ajuste de inventario (spec 006, T4), sin React para poder probarlo. Las reglas son las del
// servidor (inventory/adjustments.py); aquí se avisan antes de enviar.
import type { AdjustmentReason, Product } from "./api";
import { centsToApi } from "./money";
import { priceToCents } from "./productForm";

export type Direction = "IN" | "OUT";

/** Motivos que se eligen en la pantalla ("conteo físico" lo genera el conteo) y su sentido. */
export const REASONS: { id: Exclude<AdjustmentReason, "PHYSICAL_COUNT">; label: string; direction: Direction | "BOTH" }[] = [
  { id: "DAMAGE", label: "Daño", direction: "OUT" },
  { id: "LOSS", label: "Pérdida o robo", direction: "OUT" },
  { id: "INTERNAL_USE", label: "Uso interno", direction: "OUT" },
  { id: "EXPIRED", label: "Vencimiento o mal estado", direction: "OUT" },
  { id: "SURPLUS", label: "Sobrante", direction: "IN" },
  { id: "RECORD_ERROR", label: "Error de registro", direction: "BOTH" },
];

export interface DraftLine {
  key: string;
  product: Product;
  unit: string;
  quantity: string;
  direction: Direction;
  /** Solo para sobrantes de un producto sin costo; por la unidad elegida. */
  cost: string;
}

/** El sentido que manda el motivo; con "error de registro" se respeta el que eligió el usuario. */
export function directionFor(reason: string, current: Direction): Direction {
  const fixed = REASONS.find((r) => r.id === reason)?.direction;
  return fixed === "IN" || fixed === "OUT" ? fixed : current;
}

export function newLine(product: Product, unit: string, reason: string): DraftLine {
  return { key: crypto.randomUUID(), product, unit, quantity: "1", direction: directionFor(reason, "OUT"), cost: "" };
}

export function adjustmentBody(form: { clientUuid: string; warehouse: number | null; reason: string; note: string; lines: DraftLine[] }):
  { body: Record<string, unknown> } | { error: string } {
  if (!form.warehouse) return { error: "Elige la bodega." };
  if (!REASONS.some((r) => r.id === form.reason)) return { error: "Elige el motivo." };
  if (!form.note.trim()) return { error: "Escribe una nota: qué pasó con la mercancía." };
  if (form.lines.length === 0) return { error: "Agrega al menos un producto." };
  const lines = [];
  for (const line of form.lines) {
    const quantity = Number(line.quantity.replace(",", "."));
    if (!(quantity > 0)) return { error: `${line.product.sku}: la cantidad debe ser mayor que cero.` };
    const direction = directionFor(form.reason, line.direction);
    const item: Record<string, unknown> = { product: line.product.id, unit: line.unit, quantity: String(quantity), direction };
    if (direction === "IN" && line.cost.trim()) {
      const cents = priceToCents(line.cost);
      if (cents == null) return { error: `${line.product.sku}: escribe el costo como 12500 o 12.500,50.` };
      item.unit_cost = centsToApi(cents);
    }
    lines.push(item);
  }
  return { body: { client_uuid: form.clientUuid, warehouse: form.warehouse, reason: form.reason, note: form.note.trim(), lines } };
}
