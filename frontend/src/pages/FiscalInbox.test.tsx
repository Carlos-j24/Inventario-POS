import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { FiscalDocumentDetail, FiscalDocumentRow, FiscalInbox as Inbox } from "../api";
import { AuthProvider } from "../auth";
import FiscalInbox, { inboxUrl } from "./FiscalInbox";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

const row = (over: Partial<FiscalDocumentRow> = {}): FiscalDocumentRow => ({
  id: 1, kind: "POS", kind_label: "Documento equivalente POS", code: "CJ11", status: "PENDING", status_label: "Pendiente de envío",
  sale: 10, sale_number: "V-000010", register: "CAJA1", customer: "Consumidor final", customer_id: 1, total: "84000.00",
  issued_at: "2026-10-17T15:00:00Z", attempts: 0, last_error: "", next_attempt_at: null, validated_at: null, cude: "",
  deadline: "2026-10-19T15:00:00Z", alert: null, waiting_for: null, ...over,
});

const inbox: Inbox = {
  summary: { pending: 3, rejected: 1, overdue: 1, due_soon: 1 },
  results: [
    row({ id: 1, code: "CJ11", alert: "overdue" }),
    row({ id: 2, code: "CJ12", alert: "due_soon" }),
    row({ id: 3, code: "FE11", kind: "INVOICE", kind_label: "Factura electrónica", status: "REJECTED", customer: "Constructora SAS", last_error: "NIT inválido", attempts: 1 }),
    row({ id: 4, code: "NA1", kind: "POS_ADJUSTMENT", kind_label: "Nota de ajuste", waiting_for: "CJ11" }),
  ],
};

const rejected: FiscalDocumentDetail = {
  ...inbox.results[2], subtotal: "70588.24", tax: "13411.76", qr_data: "", corrects: null,
  events: [
    { at: "2026-10-17T15:00:00Z", kind: "created", detail: "Venta V-000011" },
    { at: "2026-10-17T15:01:00Z", kind: "rejected", detail: "NIT inválido" },
  ],
};

function mockApi(routes: Record<string, () => Response>) {
  const fn = vi.fn((url: string, init?: RequestInit) => {
    const route = routes[`${init?.method ?? "GET"} ${url}`];
    return route ? Promise.resolve(route()) : Promise.reject(new Error(`ruta no simulada: ${init?.method ?? "GET"} ${url}`));
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => vi.unstubAllGlobals());

const history = () => screen.getAllByRole("listitem").map((li) => li.textContent);

const base = {
  "GET /api/invoicing/documents/": () => json(inbox),
  "GET /api/invoicing/documents/?status=REJECTED": () => json({ ...inbox, results: [inbox.results[2]] }),
  "GET /api/invoicing/documents/3/": () => json(rejected),
};

const me = (permissions: string[]) => ({
  id: 1, username: "sofia", first_name: "", last_name: "", roles: ["Supervisor"], permissions, must_change_password: false,
});

describe("bandeja de documentos DIAN", () => {
  it("resume pendientes, rechazados y plazos, y marca cada documento", async () => {
    mockApi(base);
    render(<FiscalInbox />);
    const summary = await screen.findByLabelText("Resumen");
    expect(summary).toHaveTextContent(/3 pendientes.*1 rechazados.*1 con plazo vencido.*1 por vencer/);
    const table = screen.getByRole("table", { name: "Documentos" });
    expect(within(table).getByRole("row", { name: /^CJ11 / })).toHaveTextContent("Plazo vencido");
    expect(within(table).getByRole("row", { name: /^CJ12 / })).toHaveTextContent("Vence pronto");
    expect(within(table).getByRole("row", { name: /FE11/ })).toHaveTextContent(/Constructora SAS.*Rechazado/);
    expect(within(table).getByRole("row", { name: /NA1/ })).toHaveTextContent("Espera CJ11");
  });

  it("el filtro cambia la consulta", async () => {
    const fetch = mockApi(base);
    render(<FiscalInbox />);
    await screen.findByLabelText("Resumen");
    await userEvent.click(screen.getByRole("button", { name: "Rechazados" }));
    expect(await screen.findByRole("row", { name: /FE11/ })).toBeInTheDocument();
    expect(screen.queryByRole("row", { name: /^CJ11 / })).not.toBeInTheDocument();
    expect(fetch.mock.calls.map(([u]) => u)).toContain("/api/invoicing/documents/?status=REJECTED");
    expect(inboxUrl("")).toBe("/api/invoicing/documents/");
  });

  it("muestra el historial y el supervisor reintenta un rechazado", async () => {
    const fetch = mockApi({
      ...base,
      "GET /api/auth/csrf/": () => new Response(null, { status: 204 }),
      "GET /api/auth/me/": () => json(me(["reports.view", "sales.void"])),
      "POST /api/invoicing/documents/3/retry/": () => json({ ...rejected, status: "PENDING", last_error: "", events: [...rejected.events, { at: "2026-10-17T16:00:00Z", kind: "retry", detail: "Reintento pedido por sofia" }] }),
    });
    render(<AuthProvider><FiscalInbox /></AuthProvider>);
    await userEvent.click(await screen.findByRole("button", { name: "FE11" }));
    expect(await screen.findByRole("heading", { name: "FE11" })).toBeInTheDocument();
    expect(screen.getByText("NIT inválido", { selector: "p" })).toBeInTheDocument();
    expect(history()).toContainEqual(expect.stringMatching(/Rechazado — NIT inválido$/));

    await userEvent.click(screen.getByRole("button", { name: "Reintentar envío" }));
    await screen.findByText("Reintento");
    expect(history().at(-1)).toMatch(/Reintento — Reintento pedido por sofia$/);
    expect(screen.queryByRole("button", { name: "Reintentar envío" })).not.toBeInTheDocument();
    expect(fetch.mock.calls.filter(([u]) => u === "/api/invoicing/documents/").length).toBe(2); // recarga la lista
  });

  it("sin sales.void no se ofrece reintentar", async () => {
    mockApi({
      ...base,
      "GET /api/auth/csrf/": () => new Response(null, { status: 204 }),
      "GET /api/auth/me/": () => json(me(["reports.view"])),
    });
    render(<AuthProvider><FiscalInbox /></AuthProvider>);
    await userEvent.click(await screen.findByRole("button", { name: "FE11" }));
    await screen.findByRole("heading", { name: "FE11" });
    expect(screen.queryByRole("button", { name: "Reintentar envío" })).not.toBeInTheDocument();
  });

  it("muestra los errores del servidor", async () => {
    mockApi({ "GET /api/invoicing/documents/": () => json({ detail: "No tienes el permiso 'reports.view'." }, 403) });
    render(<FiscalInbox />);
    expect(await screen.findByRole("alert")).toHaveTextContent("reports.view");
  });
});
