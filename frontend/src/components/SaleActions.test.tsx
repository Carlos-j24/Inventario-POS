import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Register, SaleDetail } from "../api";
import { SaleDetailView } from "../pages/Sales";
import { remaining, whyNotVoid } from "./SaleActions";

const sale: SaleDetail = {
  id: 8, number: "V-000008", occurred_at: "2026-10-16T19:20:00Z", register: "CAJA1", seller: "laura",
  salesperson: "andres", order_code: null, total: "68000.00", status: "COMPLETED", offline: false, needs_review: false,
  shift_open: true, subtotal: "57142.86", tax: "10857.14", void_reason: "", voided_at: null, reviewed_at: null, review_note: "",
  lines: [
    { id: 1, product: "CAB-12", name: "Cable", unit: "m", quantity: "12.500", returned_quantity: "0", unit_price: "3200.00", catalog_price: "3200.00", total: "40000.00" },
    { id: 2, product: "MAR-16", name: "Martillo", unit: "und", quantity: "2.000", returned_quantity: "1.000", unit_price: "14000.00", catalog_price: "14000.00", total: "28000.00" },
  ],
  payments: [{ method: "CASH", amount: "68000.00", received: "68000.00", change: "0.00", reference: "" }],
  returns: [],
};

const registers: Register[] = [
  { id: 2, code: "CAJA2", name: "Caja 2", warehouse: "PRAL", open_shift: 21 },
  { id: 1, code: "CAJA1", name: "Caja 1", warehouse: "PRAL", open_shift: 13 },
  { id: 3, code: "CAJA3", name: "Caja 3", warehouse: "PRAL", open_shift: null },
];

type Route = (url: string, method: string, body: unknown) => Response | undefined;

function mockApi(route: Route) {
  const fn = vi.fn((url: string, init?: RequestInit) => {
    const res = route(url, init?.method ?? "GET", init?.body ? JSON.parse(String(init.body)) : undefined);
    return res ? Promise.resolve(res) : Promise.reject(new Error(`ruta no simulada: ${init?.method ?? "GET"} ${url}`));
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const posts = (fetch: ReturnType<typeof mockApi>, url: string) =>
  fetch.mock.calls.filter(([u, i]) => u === url && i?.method === "POST").map(([, i]) => JSON.parse(String(i?.body)));

afterEach(() => vi.unstubAllGlobals());

describe("reglas", () => {
  it("lo que queda por devolver descuenta lo ya devuelto", () => {
    expect(sale.lines.map(remaining)).toEqual([12.5, 1]);
  });

  it("explica por qué no se anula", () => {
    expect(whyNotVoid(sale)).toBeNull();
    expect(whyNotVoid({ ...sale, shift_open: false })).toMatch(/turno ya cerró/);
    expect(whyNotVoid({ ...sale, returns: [{ id: 1, number: "D-1", reason: "", total: "1", refund_method: "CASH", user: "", created_at: "" }] })).toMatch(/devoluciones/);
  });
});

describe("anular", () => {
  it("anula con motivo y vuelve a cargar la venta ya anulada", async () => {
    let voided = false;
    const onChanged = vi.fn();
    const fetch = mockApi((url, method) => {
      if (url === "/api/sales/8/" && method === "GET") return json(voided ? { ...sale, status: "VOIDED", void_reason: "Error de caja" } : sale);
      if (url === "/api/sales/8/void/") { voided = true; return json({ ...sale, status: "VOIDED" }); }
    });
    render(<SaleDetailView id={8} canAct onChanged={onChanged} />);
    await userEvent.click(await screen.findByRole("button", { name: "Anular venta" }));
    const confirm = screen.getAllByRole("button", { name: "Anular venta" }).at(-1)!;
    expect(confirm).toBeDisabled(); // sin motivo no se puede
    await userEvent.type(screen.getByPlaceholderText("Error de digitación"), "Error de caja");
    await userEvent.click(confirm);

    expect(await screen.findByText("Anulada: Error de caja")).toBeInTheDocument();
    expect(posts(fetch, "/api/sales/8/void/")).toEqual([{ reason: "Error de caja" }]);
    expect(onChanged).toHaveBeenCalled();
  });

  it("con el turno cerrado no deja anular y lo explica", async () => {
    mockApi((url) => (url === "/api/sales/8/" ? json({ ...sale, shift_open: false }) : undefined));
    render(<SaleDetailView id={8} canAct />);
    expect(await screen.findByRole("button", { name: "Anular venta" })).toBeDisabled();
    expect(screen.getByText(/turno ya cerró/)).toBeInTheDocument();
  });

  it("sin el permiso no aparecen las acciones", async () => {
    mockApi((url) => (url === "/api/sales/8/" ? json(sale) : undefined));
    render(<SaleDetailView id={8} />);
    await screen.findByRole("heading", { name: "V-000008" });
    expect(screen.queryByRole("button", { name: "Anular venta" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Devolver" })).not.toBeInTheDocument();
  });
});

describe("devolver", () => {
  function setup(regs = registers) {
    const fetch = mockApi((url, method) => {
      if (url === "/api/sales/8/" && method === "GET") return json(sale);
      if (url === "/api/cash/registers/") return json(regs);
      if (url === "/api/sales/8/returns/") return json({ id: 1, number: "D-000001", total: "14000.00" }, 201);
    });
    render(<SaleDetailView id={8} canAct />);
    return fetch;
  }

  it("devuelve parte, por defecto desde la caja de la venta, con un client_uuid", async () => {
    const fetch = setup();
    await userEvent.click(await screen.findByRole("button", { name: "Devolver" }));
    expect(await screen.findByLabelText("Caja del reembolso")).toHaveValue("13"); // turno de CAJA1
    await userEvent.type(screen.getByLabelText("Devolver Martillo"), "1");
    await userEvent.type(screen.getByPlaceholderText("El cliente no lo necesitó"), "Defectuoso");
    expect(screen.getByText(/Reembolso estimado/)).toHaveTextContent("14.000");
    await userEvent.click(screen.getByRole("button", { name: "Registrar devolución" }));

    const [body] = posts(fetch, "/api/sales/8/returns/");
    expect(body).toMatchObject({ shift: 13, refund_method: "CASH", reason: "Defectuoso", lines: [{ line: 2, quantity: "1" }] });
    expect(body.client_uuid).toMatch(/^[0-9a-f-]{36}$/);
  });

  it("no deja devolver más de lo que queda", async () => {
    setup();
    await userEvent.click(await screen.findByRole("button", { name: "Devolver" }));
    await userEvent.type(screen.getByLabelText("Devolver Martillo"), "2"); // vendió 2, ya devolvió 1
    await userEvent.type(screen.getByPlaceholderText("El cliente no lo necesitó"), "x");
    expect(screen.getByText(/solo se pueden devolver 1/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Registrar devolución" })).toBeDisabled();
  });

  it("sin cajas con turno abierto avisa y no deja registrar", async () => {
    setup([registers[2]]);
    await userEvent.click(await screen.findByRole("button", { name: "Devolver" }));
    expect(await screen.findByText(/No hay ninguna caja con turno abierto/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Devolver Cable"), "1");
    await userEvent.type(screen.getByPlaceholderText("El cliente no lo necesitó"), "x");
    expect(screen.getByRole("button", { name: "Registrar devolución" })).toBeDisabled();
  });
});
