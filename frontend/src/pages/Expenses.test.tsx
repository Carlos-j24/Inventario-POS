import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Expense, ExpenseCategory, ExpenseList } from "../api";
import Expenses from "./Expenses";

const URL = "/api/expenses/";
const categories: ExpenseCategory[] = [
  { id: 1, name: "Arriendo", is_active: true }, { id: 2, name: "Insumos", is_active: true }, { id: 3, name: "Publicidad", is_active: false },
];
const expense = (over: Partial<Expense> = {}): Expense => ({
  id: 4, spent_on: "2026-11-02", amount: "15000.00", category: 2, category_name: "Insumos", note: "Jabón", register: null,
  status: "ACTIVE", created_by: "dueno", created_at: "2026-11-02T15:00:00Z", void_reason: "", voided_by: null, voided_at: null,
  events: [{ kind: "CREATED", label: "Anotado", detail: "$15.000 en Insumos", user: "dueno", at: "2026-11-02T15:00:00Z" }], ...over,
});
const list = (rows: Expense[], total = "15000.00"): ExpenseList => ({ from: "2026-11-01", to: "2026-11-03", total, expenses: rows });

type Handler = (body: Record<string, unknown> | undefined) => Response;
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

function mockApi(routes: Record<string, Handler>) {
  const fn = vi.fn((url: string, init?: RequestInit) => {
    const key = `${init?.method ?? "GET"} ${url}`;
    const h = routes[key];
    return h ? Promise.resolve(h(init?.body ? JSON.parse(String(init.body)) : undefined)) : Promise.reject(new Error(`no simulada: ${key}`));
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}
const bodies = (fetch: ReturnType<typeof mockApi>, key: string) =>
  fetch.mock.calls.filter(([u, i]) => `${i?.method ?? "GET"} ${u}` === key).map(([, i]) => (i?.body ? JSON.parse(String(i.body)) : undefined));
const MONTH = `GET ${URL}?from=2026-11-01&to=2026-11-03`;
const base = { [`GET ${URL}categories/`]: () => json(categories) };
const panel = () => screen.getByRole("complementary");

beforeEach(() => { vi.useFakeTimers({ toFake: ["Date"] }); vi.setSystemTime(new Date("2026-11-03T15:00:00-05:00")); });
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

describe("pantalla Gastos (spec 013)", () => {
  it("muestra los gastos del mes con su total y cambia de periodo", async () => {
    const fetch = mockApi({
      ...base,
      [MONTH]: () => json(list([expense(), expense({ id: 5, status: "VOIDED", note: "Repetido", register: { name: "Caja 1", shift_open: true } })])),
      [`GET ${URL}?from=2026-10-01&to=2026-11-03`]: () => json(list([], "0.00")),
    });
    render(<Expenses />);
    const table = await screen.findByRole("table", { name: "Gastos del periodo" });
    expect(await within(table).findByRole("row", { name: /Jabón/ })).toHaveTextContent("InsumosJabón$ 15.000");
    expect(within(table).getByRole("row", { name: /Repetido/ })).toHaveTextContent("Repetido · de Caja 1$ 15.000Anulado");
    expect(table).toHaveTextContent("Total (sin anulados)$ 15.000");
    fireEvent.change(screen.getByLabelText("Desde"), { target: { value: "2026-10-01" } });
    expect(await within(table).findByText("Sin gastos en el periodo.")).toBeInTheDocument();
    expect(fetch.mock.calls.some(([u]) => u === `${URL}?from=2026-10-01&to=2026-11-03`)).toBe(true);
  });

  it("anota un gasto pagado de la caja con turno abierto", async () => {
    const created = expense({ id: 9, spent_on: "2026-11-03", register: { name: "Caja 1", shift_open: true } });
    const fetch = mockApi({
      ...base, [MONTH]: () => json(list([])),
      "GET /api/cash/registers/": () => json([
        { id: 1, code: "CAJA1", name: "Caja 1", warehouse: "PRAL", open_shift: 13 },
        { id: 2, code: "CAJA2", name: "Caja 2", warehouse: "PRAL", open_shift: null },
      ]),
      [`POST ${URL}`]: () => json(created, 201),
      [`GET ${URL}9/`]: () => json(created),
    });
    render(<Expenses />);
    await userEvent.click(await screen.findByRole("button", { name: "Anotar gasto" }));
    const form = within(panel()).getByRole("form", { name: "Anotar gasto" });
    const save = within(form).getByRole("button", { name: "Anotar" });
    expect(save).toBeDisabled();
    await userEvent.type(within(form).getByLabelText("Valor"), "15.000");
    expect(form).toHaveTextContent("Elige la categoría.");
    const category = within(form).getByLabelText("Categoría");
    expect(within(category).queryByRole("option", { name: "Publicidad" })).not.toBeInTheDocument(); // desactivada
    await userEvent.selectOptions(category, "Insumos");
    await userEvent.type(within(form).getByLabelText("Nota"), "Jabón");
    await userEvent.click(await within(form).findByLabelText(/Pagado de la caja/));
    expect(within(form).queryByLabelText("Caja")).not.toBeInTheDocument(); // una sola con turno: va sola
    await userEvent.click(save);
    expect(bodies(fetch, `POST ${URL}`)).toEqual([{ spent_on: "2026-11-03", amount: "15000.00", category: 2, note: "Jabón", register: 1 }]);
    expect(await within(panel()).findByRole("heading", { name: /^Insumos · \$\s15\.000$/ })).toBeInTheDocument();
    expect(panel()).toHaveTextContent("pagado de Caja 1");
  });

  it("muestra el error del servidor al anotar", async () => {
    mockApi({
      ...base, [MONTH]: () => json(list([])), "GET /api/cash/registers/": () => json([]),
      [`POST ${URL}`]: () => json({ category: ["La categoría Insumos está desactivada."] }, 400),
    });
    render(<Expenses />);
    await userEvent.click(await screen.findByRole("button", { name: "Anotar gasto" }));
    const form = within(panel()).getByRole("form", { name: "Anotar gasto" });
    expect(await within(form).findByText("Ninguna caja tiene el turno abierto.")).toBeInTheDocument();
    expect(within(form).getByLabelText(/Pagado de la caja/)).toBeDisabled();
    await userEvent.type(within(form).getByLabelText("Valor"), "15000");
    await userEvent.selectOptions(await within(form).findByLabelText("Categoría"), "Insumos");
    await userEvent.click(within(form).getByRole("button", { name: "Anotar" }));
    expect(await within(form).findByRole("alert")).toHaveTextContent("desactivada");
  });

  it("corrige solo lo que cambió, anula con motivo y deja la historia", async () => {
    const corrected = expense({
      amount: "18000.00",
      events: [...expense().events, { kind: "CHANGED", label: "Corregido", detail: "valor $15.000 → $18.000", user: "dueno", at: "2026-11-03T15:00:00Z" }],
    });
    const fetch = mockApi({
      ...base, [MONTH]: () => json(list([expense()])), [`GET ${URL}4/`]: () => json(expense()),
      [`PATCH ${URL}4/`]: () => json(corrected),
      [`POST ${URL}4/void/`]: () => json({ ...corrected, status: "VOIDED", void_reason: "Repetido" }),
    });
    render(<Expenses />);
    await userEvent.click(await screen.findByRole("button", { name: "2 de nov de 2026" }));
    const fix = await within(panel()).findByRole("form", { name: "Corregir gasto" });
    const save = within(fix).getByRole("button", { name: "Guardar corrección" });
    expect(save).toBeDisabled();
    await userEvent.clear(within(fix).getByLabelText("Valor"));
    await userEvent.type(within(fix).getByLabelText("Valor"), "18000");
    await userEvent.click(save);
    expect(bodies(fetch, `PATCH ${URL}4/`)).toEqual([{ amount: "18000.00" }]);
    expect(await within(panel()).findByRole("status")).toHaveTextContent("Gasto corregido.");
    expect(within(panel()).getByRole("list", { name: "Historia del gasto" })).toHaveTextContent("Corregido (dueno) · valor $15.000 → $18.000");

    const anul = within(panel()).getByRole("button", { name: "Anular gasto" });
    expect(anul).toBeDisabled();
    await userEvent.type(within(panel()).getByLabelText("Motivo de la anulación"), "Repetido");
    await userEvent.click(anul);
    expect(bodies(fetch, `POST ${URL}4/void/`)).toEqual([{ reason: "Repetido" }]);
    expect(await within(panel()).findByText("Anulado: Repetido")).toBeInTheDocument();
    expect(within(panel()).queryByRole("form", { name: "Corregir gasto" })).not.toBeInTheDocument();
    expect(within(panel()).queryByRole("button", { name: "Anular gasto" })).not.toBeInTheDocument();
  });

  it("de una caja con el turno cerrado: el valor y la fecha no cambian y no se anula", async () => {
    const closed = expense({ register: { name: "Caja 1", shift_open: false } });
    mockApi({ ...base, [MONTH]: () => json(list([closed])), [`GET ${URL}4/`]: () => json(closed) });
    render(<Expenses />);
    await userEvent.click(await screen.findByRole("button", { name: "2 de nov de 2026" }));
    const fix = await within(panel()).findByRole("form", { name: "Corregir gasto" });
    expect(within(fix).getByLabelText("Valor")).toBeDisabled();
    expect(within(fix).getByLabelText("Fecha")).toBeDisabled();
    expect(within(fix).getByLabelText("Nota")).toBeEnabled();
    expect(panel()).toHaveTextContent("Salió de Caja 1 y su turno ya cerró");
    expect(within(panel()).queryByRole("button", { name: "Anular gasto" })).not.toBeInTheDocument();
  });

  it("el administrador agrega y desactiva categorías", async () => {
    const fetch = mockApi({
      ...base, [MONTH]: () => json(list([])),
      [`PATCH ${URL}categories/2/`]: () => json({ id: 2, name: "Insumos", is_active: false }),
      [`POST ${URL}categories/`]: () => json({ id: 7, name: "Transporte", is_active: true }, 201),
    });
    render(<Expenses />);
    await userEvent.click(await screen.findByRole("button", { name: "Categorías" }));
    const items = within(panel()).getByRole("list", { name: "Categorías" });
    expect(await within(items).findByText("Publicidad (desactivada)")).toBeInTheDocument();
    await userEvent.click(within(within(items).getByText("Insumos").closest("li")!).getByRole("button", { name: "Desactivar" }));
    expect(bodies(fetch, `PATCH ${URL}categories/2/`)).toEqual([{ is_active: false }]);
    await userEvent.type(within(panel()).getByLabelText("Nueva categoría"), " Transporte ");
    await userEvent.click(within(panel()).getByRole("button", { name: "Agregar" }));
    expect(bodies(fetch, `POST ${URL}categories/`)).toEqual([{ name: "Transporte" }]);
    await vi.waitFor(() => expect(within(panel()).getByLabelText("Nueva categoría")).toHaveValue(""));
  });
});
