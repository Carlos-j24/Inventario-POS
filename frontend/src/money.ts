// Dinero en centavos enteros para no arrastrar errores de coma flotante.
// Redondeo a la mitad hacia arriba, igual que el backend (ROUND_HALF_UP).

export function toCents(value: string | number): number {
  const n = typeof value === "number" ? value : Number(String(value).replace(",", "."));
  if (!Number.isFinite(n)) return 0;
  return Math.round(n * 100);
}

export function centsToApi(cents: number): string {
  return (cents / 100).toFixed(2);
}

const cop = new Intl.NumberFormat("es-CO", {
  style: "currency",
  currency: "COP",
  minimumFractionDigits: 0,
  maximumFractionDigits: 2,
});

export function formatMoney(cents: number): string {
  return cop.format(cents / 100);
}

const qty = new Intl.NumberFormat("es-CO", { maximumFractionDigits: 3 });

export function formatQty(value: string | number): string {
  return qty.format(Number(value));
}
