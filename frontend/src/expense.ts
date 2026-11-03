// Gastos (spec 013, T5), sin React para poder probarlo. El servidor (expenses/services.py) decide;
// aquí se avisa antes de enviar y se arma solo lo que cambió.
import type { Expense } from "./api";
import { centsToApi, toCents } from "./money";
import { priceToCents } from "./productForm";

export interface ExpenseForm {
  spent_on: string;
  /** Lo que escribe el usuario: "15000", "15.000"… */
  amount: string;
  category: string;
  note: string;
  /** Pagado del cajón de esta caja ("" si no salió de la caja). */
  register: string;
}

export const emptyExpense = (today: string): ExpenseForm => ({ spent_on: today, amount: "", category: "", note: "", register: "" });

/** El primer día del mes de `today` (AAAA-MM-DD). */
export const monthStart = (today: string) => `${today.slice(0, 8)}01`;

/** Lo primero que falta o está mal, como lo diría el servidor, o null. */
export function expenseProblem(form: ExpenseForm, today: string): string | null {
  const cents = priceToCents(form.amount);
  if (cents == null || cents <= 0) return "Escribe el valor del gasto, como 15000 o 15.000.";
  if (!form.category) return "Elige la categoría.";
  if (!form.spent_on || form.spent_on > today) return "La fecha del gasto no puede ser futura.";
  if (form.register && form.spent_on !== today) return "Lo que sale de la caja es de hoy.";
  return null;
}

/** El cuerpo de POST /api/expenses/. */
export function newExpensePayload(form: ExpenseForm) {
  return {
    spent_on: form.spent_on,
    amount: centsToApi(priceToCents(form.amount) ?? 0),
    category: Number(form.category),
    note: form.note.trim(),
    register: form.register ? Number(form.register) : null,
  };
}

export const toExpenseForm = (e: Expense): ExpenseForm => ({
  spent_on: e.spent_on, amount: String(toCents(e.amount) / 100), category: String(e.category), note: e.note, register: "",
});

/** El cuerpo de PATCH: solo lo que cambió. */
export function changedExpense(form: ExpenseForm, original: Expense): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  if (form.spent_on !== original.spent_on) body.spent_on = form.spent_on;
  const cents = priceToCents(form.amount);
  if (cents != null && cents !== toCents(original.amount)) body.amount = centsToApi(cents);
  if (Number(form.category) !== original.category) body.category = Number(form.category);
  if (form.note.trim() !== original.note) body.note = form.note.trim();
  return body;
}

/** Lo que ya no se puede cambiar del gasto, o null si se corrige y se anula libremente. */
export function lockedReason(e: Expense): string | null {
  if (e.status === "VOIDED") return "Anulado: ya no se corrige.";
  if (e.register && !e.register.shift_open) return `Salió de ${e.register.name} y su turno ya cerró: el valor no cambia ni se anula.`;
  return null;
}
