import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { TicketData } from "../api";
import TicketDialog from "./TicketDialog";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

const pending: TicketData = {
  business: { name: "Ferretería El Tornillo SAS", trade_name: "El Tornillo", nit: "800197268-4", address: "Cra 1 # 2-3", city: "Florencia", phone: "3001234567", email: "", tax_regime: "Responsable de IVA" },
  title: "Documento equivalente electrónico POS", code: "CJ11", status: "PENDING", document_id: 9, sale_number: "V-000020",
  issued_at: "2026-10-17T17:00:00Z", register: "CAJA1", cashier: "laura.caja", customer: null,
  lines: [{ name: "Martillo 16 oz", quantity: "2.000", unit: "und", unit_price: "28000.00", total: "56000.00" }],
  subtotal: "47058.82", tax: "8941.18", total: "56000.00",
  taxes: [{ rate: "19", base: "47058.82", tax: "8941.18" }, { rate: "excluido", base: "0.00", tax: "0.00" }],
  payments: [{ label: "Efectivo", amount: "60000.00" }], change: "4000.00",
  cude: null, qr_svg: null, resolution: "Resolución DIAN 18764 del 2026-01-01: CJ11 a CJ15000, vigente hasta 2027-12-31",
  notes: ["Pendiente de validación por la DIAN."],
};
const validated: TicketData = {
  ...pending, status: "VALIDATED", cude: "ab".repeat(48), qr_svg: '<svg data-testid="qr"></svg>', notes: ["Documento validado por la DIAN"],
};

function mockApi(routes: Record<string, () => Response>) {
  const fn = vi.fn((url: string, init?: RequestInit) => {
    const route = routes[`${init?.method ?? "GET"} ${url}`];
    return route ? Promise.resolve(route()) : Promise.reject(new Error(`ruta no simulada: ${url}`));
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => vi.unstubAllGlobals());

describe("tiquete", () => {
  it("envía el documento pendiente y muestra el tiquete validado con QR y CUDE", async () => {
    let calls = 0;
    const fetch = mockApi({
      "GET /api/invoicing/ticket/20/": () => json(calls++ === 0 ? pending : validated),
      "POST /api/invoicing/documents/9/send/": () => json({ status: "VALIDATED", last_error: "" }),
    });
    const print = vi.fn();
    vi.stubGlobal("print", print);
    render(<TicketDialog saleId={20} onClose={() => {}} />);

    const ticket = await screen.findByRole("article", { name: "Tiquete" });
    await within(ticket).findByText("Documento validado por la DIAN");
    expect(ticket).toHaveTextContent("Ferretería El Tornillo SAS");
    expect(ticket).toHaveTextContent("NIT 800197268-4");
    expect(ticket).toHaveTextContent(/Responsable de IVA.*Cra 1 # 2-3, Florencia.*Tel\. 3001234567/);
    expect(ticket).toHaveTextContent(/Documento equivalente electrónico POS\s*CJ11/);
    expect(ticket).toHaveTextContent("Cliente: Consumidor final");
    expect(ticket).toHaveTextContent(/2 und Martillo 16 oz × \$\s?28\.000/);
    expect(ticket).toHaveTextContent(/Base IVA 19 % \$\s?47\.058,82.*IVA \$\s?8\.941,18/);
    expect(ticket).toHaveTextContent("Excluido de IVA");
    expect(ticket).toHaveTextContent(/Total\s*\$\s?56\.000/);
    expect(ticket).toHaveTextContent(/Vueltas\s*\$\s?4\.000/);
    expect(within(ticket).getByTestId("qr")).toBeInTheDocument();
    expect(ticket).toHaveTextContent(`CUDE: ${"ab".repeat(48)}`);
    expect(ticket).toHaveTextContent("Resolución DIAN 18764");
    expect(fetch.mock.calls.map(([u, i]) => `${(i as RequestInit | undefined)?.method ?? "GET"} ${u}`)).toEqual([
      "GET /api/invoicing/ticket/20/", "POST /api/invoicing/documents/9/send/", "GET /api/invoicing/ticket/20/",
    ]);

    await userEvent.click(screen.getByRole("button", { name: "Imprimir" }));
    expect(print).toHaveBeenCalled();
  });

  it("si ya está validado no lo reenvía", async () => {
    const fetch = mockApi({ "GET /api/invoicing/ticket/20/": () => json(validated) });
    render(<TicketDialog saleId={20} onClose={() => {}} />);
    await screen.findByText("Documento validado por la DIAN");
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("aunque el envío falle, muestra el tiquete pendiente", async () => {
    mockApi({
      "GET /api/invoicing/ticket/20/": () => json(pending),
      "POST /api/invoicing/documents/9/send/": () => json({ detail: "error" }, 500),
    });
    render(<TicketDialog saleId={20} onClose={() => {}} />);
    expect(await screen.findByText("Pendiente de validación por la DIAN.")).toBeInTheDocument();
  });

  it("el tiquete de contingencia se imprime sin servidor, con el cliente si lo hay", async () => {
    const fetch = mockApi({});
    const onClose = vi.fn();
    render(<TicketDialog data={{ ...pending, title: "Documento de contingencia", code: "CT21", status: null, customer: { name: "Ana", document: "Cédula 1020" } }} onClose={onClose} />);
    expect(screen.getByRole("article", { name: "Tiquete" })).toHaveTextContent(/Documento de contingencia\s*CT21.*Cliente: Ana · Cédula 1020/);
    expect(fetch).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Cerrar" }));
    expect(onClose).toHaveBeenCalled();
  });

  it("muestra el error si no se pudo cargar", async () => {
    mockApi({ "GET /api/invoicing/ticket/20/": () => json({ detail: "No encontrado." }, 404) });
    render(<TicketDialog saleId={20} onClose={() => {}} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("No encontrado.");
  });
});
