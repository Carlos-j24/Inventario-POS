import { describe, expect, it } from "vitest";

import type { Expense } from "./api";
import { changedExpense, emptyExpense, expenseProblem, lockedReason, monthStart, newExpensePayload, toExpenseForm } from "./expense";

const today = "2026-11-03";
const soap: Expense = {
  id: 4, spent_on: "2026-11-02", amount: "15000.00", category: 2, category_name: "Insumos", note: "Jabón", register: null,
  status: "ACTIVE", created_by: "dueno", created_at: "2026-11-02T15:00:00Z", void_reason: "", voided_by: null, voided_at: null, events: [],
};

describe("gastos (spec 013)", () => {
  it("el periodo empieza el primero del mes", () => {
    expect(monthStart(today)).toBe("2026-11-01");
    expect(emptyExpense(today)).toEqual({ spent_on: today, amount: "", category: "", note: "", register: "" });
  });

  it("avisa lo que falta antes de enviar", () => {
    const form = { ...emptyExpense(today), amount: "15.000", category: "2" };
    expect(expenseProblem(form, today)).toBeNull();
    expect(expenseProblem({ ...form, amount: "" }, today)).toMatch(/valor/);
    expect(expenseProblem({ ...form, amount: "0" }, today)).toMatch(/valor/);
    expect(expenseProblem({ ...form, amount: "abc" }, today)).toMatch(/valor/);
    expect(expenseProblem({ ...form, category: "" }, today)).toBe("Elige la categoría.");
    expect(expenseProblem({ ...form, spent_on: "2026-11-04" }, today)).toMatch(/futura/);
    expect(expenseProblem({ ...form, register: "1", spent_on: "2026-11-02" }, today)).toBe("Lo que sale de la caja es de hoy.");
    expect(expenseProblem({ ...form, register: "1" }, today)).toBeNull();
  });

  it("arma el gasto nuevo, de la caja o no", () => {
    const form = { ...emptyExpense(today), amount: "15.000", category: "2", note: " Jabón " };
    expect(newExpensePayload(form)).toEqual({ spent_on: today, amount: "15000.00", category: 2, note: "Jabón", register: null });
    expect(newExpensePayload({ ...form, register: "1" }).register).toBe(1);
  });

  it("la corrección manda solo lo que cambió", () => {
    const form = toExpenseForm(soap);
    expect(form).toEqual({ spent_on: "2026-11-02", amount: "15000", category: "2", note: "Jabón", register: "" });
    expect(changedExpense(form, soap)).toEqual({});
    expect(changedExpense({ ...form, amount: "18.000", category: "1", note: "Jabón y cera ", spent_on: "2026-11-01" }, soap)).toEqual({
      amount: "18000.00", category: 1, note: "Jabón y cera", spent_on: "2026-11-01",
    });
  });

  it("anulado, o de una caja ya cerrada, no se cambia como antes", () => {
    expect(lockedReason(soap)).toBeNull();
    expect(lockedReason({ ...soap, register: { name: "Caja 1", shift_open: true } })).toBeNull();
    expect(lockedReason({ ...soap, register: { name: "Caja 1", shift_open: false } })).toMatch(/Caja 1 y su turno ya cerró/);
    expect(lockedReason({ ...soap, status: "VOIDED" })).toMatch(/Anulado/);
  });
});
