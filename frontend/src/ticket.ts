// Tiquete de una venta sin conexión (spec 005, T5 y T6): lo arma el POS con lo que tiene en el
// equipo, porque no hay servidor. Usa los mismos datos que el tiquete del servidor (TicketData).
import type { Business, PaymentMethod, TicketData } from "./api";
import { linePriceCents, lineTotalCents, type CartLine } from "./cart";
import { centsToApi } from "./money";

const METHOD_LABEL: Record<PaymentMethod, string> = { CASH: "Efectivo", CARD: "Tarjeta", TRANSFER: "Transferencia" };

/** Base e IVA de un valor que ya trae el IVA, redondeado al centavo como el servidor (split_tax). */
export function splitTax(totalCents: number, rate: number): { base: number; tax: number } {
  const base = Math.round(totalCents / (1 + rate / 100));
  return { base, tax: totalCents - base };
}

export function offlineTicket({ business, lines, payments, changeCents, contingencyCode, cashier, register, now = new Date() }: {
  business: Business | null;
  lines: CartLine[];
  payments: { method: PaymentMethod; amountCents: number }[];
  changeCents: number;
  contingencyCode: string | null;
  cashier: string;
  register: string;
  now?: Date;
}): TicketData {
  const taxes = new Map<string, { base: number; tax: number }>();
  let subtotal = 0;
  let tax = 0;
  let total = 0;
  for (const line of lines) {
    const lineTotal = lineTotalCents(line);
    const key = line.product.vat_excluded ? "excluido" : line.product.tax_rate;
    const split = splitTax(lineTotal, Number(line.product.tax_rate)); // excluido siempre va con tarifa 0 %
    const acc = taxes.get(key) ?? { base: 0, tax: 0 };
    taxes.set(key, { base: acc.base + split.base, tax: acc.tax + split.tax });
    subtotal += split.base;
    tax += split.tax;
    total += lineTotal;
  }
  return {
    business,
    title: contingencyCode ? "Documento de contingencia" : "Comprobante de venta sin conexión",
    code: contingencyCode,
    status: null,
    sale_number: null,
    issued_at: now.toISOString(),
    register,
    cashier,
    customer: null,
    lines: lines.map((l) => ({
      name: l.product.name, quantity: String(l.quantity), unit: l.unit,
      unit_price: centsToApi(linePriceCents(l)), total: centsToApi(lineTotalCents(l)),
    })),
    subtotal: centsToApi(subtotal),
    tax: centsToApi(tax),
    total: centsToApi(total),
    taxes: [...taxes.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([rate, v]) => ({
      rate, base: centsToApi(v.base), tax: centsToApi(v.tax),
    })),
    payments: payments.map((p) => ({ label: METHOD_LABEL[p.method], amount: centsToApi(p.amountCents) })),
    change: centsToApi(changeCents),
    cude: null,
    qr_svg: null,
    resolution: null,
    notes: [
      contingencyCode
        ? "Emitido sin conexión (contingencia): se transmitirá a la DIAN al volver la conexión."
        : "Venta sin conexión: el documento electrónico se genera al volver la conexión.",
    ],
  };
}
