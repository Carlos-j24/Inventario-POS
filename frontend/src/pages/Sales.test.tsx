import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { SaleDetail, SaleListItem } from "../api";
import Sales, { salesQuery, todayIso } from "./Sales";

const row = (over: Partial<SaleListItem> = {}): SaleListItem => ({
  id: 8, number: "V-000008", occurred_at: "2026-10-16T19:20:00Z", register: "CAJA1", seller: "laura",
  salesperson: "andres", order_code: 4193, total: "68000.00", status: "COMPLETED", offline: false, needs_review: false,
  ...over,
});

const detail: SaleDetail = {
  ...row(), shift_open: true, subtotal: "57142.86", tax: "10857.14", void_reason: "", voided_at: null,
  reviewed_at: null, review_note: "",
  lines: [
    { id: 1, product: "CAB-12", name: "Cable THHN calibre 12", unit: "m", quantity: "12.500", returned_quantity: "0", unit_price: "3200.00", catalog_price: "3200.00", total: "40000.00" },
    { id: 2, product: "MAR-16", name: "Martillo 16 oz", unit: "und", quantity: "1.000", returned_quantity: "1.000", unit_price: "28000.00", catalog_price: "30000.00", total: "28000.00" },
  ],
  payments: [{ method: "CASH", amount: "68000.00", received: "70000.00", change: "2000.00", reference: "" }],
  returns: [{ id: 1, number: "D-000001", reason: "No le sirvió", total: "28000.00", refund_method: "CASH", user: "sofia", created_at: "2026-10-16T20:00:00Z" }],
};

type Route = (url: string) => Response | undefined;

function mockApi(route: Route) {
  const fn = vi.fn((url: string) => {
    const res = route(url);
    return res ? Promise.resolve(res) : Promise.reject(new Error(`ruta no simulada: ${url}`));
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

afterEach(() => vi.unstubAllGlobals());

describe("salesQuery", () => {
  const base = { number: "", date: todayIso(), register: "", status: "", review: false };

  it("sin filtros pide las de hoy al servidor (sin fecha)", () => {
    expect(salesQuery(base)).toBe("/api/sales/");
  });

  it("el número manda: busca en cualquier fecha", () => {
    expect(salesQuery({ ...base, number: " V-000123 ", date: "2026-01-01" })).toBe("/api/sales/?number=V-000123");
  });

  it("combina fecha, caja, estado y revisión", () => {
    expect(salesQuery({ number: "", date: "2026-10-01", register: "2", status: "VOIDED", review: true }))
      .toBe("/api/sales/?date=2026-10-01&register=2&status=VOIDED&needs_review=1");
  });
});

describe("pantalla Ventas", () => {
  it("lista las de hoy con vendedor y cajero, y muestra el detalle al elegir una", async () => {
    const fetch = mockApi((url) => {
      if (url === "/api/cash/registers/") return json([{ id: 1, code: "CAJA1", name: "Caja 1", warehouse: "PRAL", open_shift: 3 }]);
      if (url === "/api/sales/") return json([row(), row({ id: 7, number: "V-000007", salesperson: "laura", order_code: null, status: "VOIDED", total: "34500.00" })]);
      if (url === "/api/sales/8/") return json(detail);
    });
    render(<Sales />);

    const first = await screen.findByRole("row", { name: /V-000008/ });
    expect(within(first).getByText("andres / laura")).toBeInTheDocument();
    expect(within(first).getByText("Pedido 4193")).toBeInTheDocument();
    expect(screen.getByRole("row", { name: /V-000007/ })).toHaveTextContent("Anulada");
    expect(screen.getByText(/total completadas \$\s?68\.000/)).toBeInTheDocument(); // la anulada no suma

    await userEvent.click(screen.getByRole("button", { name: "V-000008" }));
    expect(await screen.findByRole("heading", { name: "V-000008" })).toBeInTheDocument();
    expect(screen.getByText(/turno abierto/)).toBeInTheDocument();
    expect(screen.getByText("devuelto 1 und")).toBeInTheDocument();
    expect(screen.getByText(/catálogo/)).toHaveTextContent("30.000"); // precio de pedido distinto al catálogo
    expect(screen.getByText(/D-000001/)).toHaveTextContent("No le sirvió");
    expect(screen.getByText(/vueltas/)).toHaveTextContent("2.000");
    expect(fetch.mock.calls.map(([u]) => u)).toContain("/api/sales/8/");
  });

  it("busca por número", async () => {
    const fetch = mockApi((url) => {
      if (url === "/api/cash/registers/") return json([]);
      if (url === "/api/sales/") return json([]);
      if (url === "/api/sales/?number=V-000008") return json([row()]);
    });
    render(<Sales />);
    expect(await screen.findByText("No hay ventas con estos filtros.")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Buscar por número"), "V-000008");
    await userEvent.click(screen.getByRole("button", { name: "Buscar" }));
    expect(await screen.findByRole("row", { name: /V-000008/ })).toBeInTheDocument();
    expect(fetch.mock.calls.map(([u]) => u)).toContain("/api/sales/?number=V-000008");
  });

  it("quien solo ve reportes no tiene filtro de caja, pero sí la lista", async () => {
    mockApi((url) => {
      if (url === "/api/cash/registers/") return json({ detail: "No tienes el permiso 'cash.operate'." }, 403);
      if (url === "/api/sales/") return json([row()]);
    });
    render(<Sales />);
    expect(await screen.findByRole("row", { name: /V-000008/ })).toBeInTheDocument();
    expect(screen.queryByLabelText("Caja")).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument(); // no es un error para él
  });
});
