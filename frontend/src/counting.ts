// Conteo físico en pantalla (spec 006, T6), sin React para poder probarlo.
import type { CountLine } from "./api";

/** El lector escribe el código y Enter: busca por código de barras (del producto o de una
 * presentación) o por SKU exacto. Devuelve la línea y la unidad en que se va a contar. */
export function findLine(lines: CountLine[], code: string): { line: CountLine; unit: string } | null {
  const c = code.trim().toLowerCase();
  if (!c) return null;
  for (const line of lines) {
    if (line.barcode?.toLowerCase() === c || line.sku.toLowerCase() === c) return { line, unit: line.base_unit };
    const unit = line.units.find((u) => u.barcode?.toLowerCase() === c);
    if (unit) return { line, unit: unit.unit };
  }
  return null;
}

/** Filtro de la lista por texto (SKU o nombre) y por "solo sin contar". */
export function filterLines(lines: CountLine[], text: string, onlyPending: boolean): CountLine[] {
  const words = text.trim().toLowerCase().split(/\s+/).filter(Boolean);
  return lines.filter((line) => {
    if (onlyPending && line.counted !== null) return false;
    const haystack = `${line.sku} ${line.name}`.toLowerCase();
    return words.every((w) => haystack.includes(w));
  });
}

/** Cantidad escrita con coma o punto decimal; null si no es un número mayor o igual a cero. */
export function parseCount(text: string): string | null {
  const clean = text.trim().replace(",", ".");
  if (!/^\d+(\.\d+)?$/.test(clean)) return null;
  return clean;
}
