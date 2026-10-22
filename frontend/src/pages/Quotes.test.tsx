import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Business, Order, Product, QuoteDetail, QuoteLine, QuoteRow } from "../api";
import { AuthProvider } from "../auth";
import Quotes from "./Quotes";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

const hammer: Product = {
  id: 2, sku: "MAR-16", name: "Martillo 16 oz", category: "Herramientas", base_unit: "und", barcode: "770MAR",
  sale_price: "28000.00", tax_rate: "19", allows_fractions: false, min_stock: "5", units: [],
};
const business: Business = { name: "Ferretería", trade_name: "", nit: "", address: "", city: "", phone: "", email: "", tax_regime: "" };

const row: QuoteRow = {
  id: 45, number: "COT-000045", customer: "Don Jorge", customer_phone: "3001234567", status: "VALID", status_label: "Vigente",
  valid_until: "2026-10-30", total: "920000.00", created_by: "andres", created_at: "2026-10-22T15:00:00Z", lines_count: 2,
};
const qline = (over: Partial<QuoteLine>): QuoteLine => ({
  id: 1, product: 2, sku: "MAR-16", name: "Martillo 16 oz", unit: "und", quantity: "10.000", unit_price: "28000.00", tax_rate: "19",
  vat_excluded: false, total: "280000.00", subtotal: "235294.12", tax: "44705.88", active: true,
  in_orders: "4.000", charged: "0.000", remaining: "6.000", ...over,
});
const detail: QuoteDetail = {
  ...row, customer_id: null, customer_document: null, note: "Entrega en obra", void_note: "", voided_by: null, duplicated_from: null,
  lines: [qline({}), qline({ id: 2, product: 1, sku: "CAB-12", name: "Cable THHN", unit: "rollo", quantity: "2.000", unit_price: "320000.00", total: "640000.00", in_orders: "0.000", remaining: "2.000" })],
  subtotal: "0", tax: "0", taxes: [], can_convert: true, business,
  orders: [{ id: 9, code: 4821, status: "PENDING", total: "112000.00", sale_number: null, created_at: "2026-10-22T16:00:00Z" }],
};
const order: Order = {
  id: 10, code: 5932, business_date: "2026-10-22", status: "PENDING", salesperson: "andres", total: "56000.00",
  created_at: "2026-10-22T17:00:00Z", sale_number: null, lines: [],
  warnings: [{ sku: "MAR-16", name: "Martillo 16 oz", kind: "bajo_minimo", available: "6.000" }],
};

type Call = { method: string; url: string; body: unknown };

function mockApi(permissions: string[], routes: Record<string, (body: unknown) => Response> = {}) {
  const calls: Call[] = [];
  const me = { id: 1, username: "andres", first_name: "", last_name: "", roles: [], permissions, must_change_password: false };
  const all: Record<string, (body: unknown) => Response> = {
    "GET /api/auth/csrf/": () => new Response(null, { status: 204 }),
    "GET /api/auth/me/": () => json(me),
    "GET /api/quotes/?status=VALID": () => json([row]),
    "GET /api/quotes/45/": () => json(detail),
    "GET /api/catalog/products/": () => json([hammer]),
    ...routes,
  };
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    const body = init?.body ? JSON.parse(init.body as string) : undefined;
    calls.push({ method, url, body });
    const route = all[`${method} ${url}`];
    return route ? Promise.resolve(route(body)) : Promise.reject(new Error(`ruta no simulada: ${method} ${url}`));
  }));
  return calls;
}

afterEach(() => vi.unstubAllGlobals());

const renderPage = () => render(<AuthProvider><Quotes /></AuthProvider>);
const vendor = ["sales.create"];

describe("pantalla Cotizaciones", () => {
  it("el vendedor cotiza a nombre del cliente y la abre", async () => {
    const created = { ...detail, id: 46, number: "COT-000046", orders: [] };
    const calls = mockApi(vendor, {
      "POST /api/quotes/": () => json(created, 201),
      "GET /api/quotes/46/": () => json(created),
    });
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "Nueva cotización" }));
    const form = screen.getByRole("form", { name: "Nueva cotización" });
    expect(within(form).getByText(/ninguno registrado \(opcional\)/)).toBeInTheDocument();
    await userEvent.click(within(form).getByRole("button", { name: "Guardar cotización" }));
    expect(within(form).getByRole("alert")).toHaveTextContent("Escribe a nombre de quién va");

    await userEvent.type(within(form).getByLabelText("A nombre de"), "Don Jorge");
    await userEvent.type(within(form).getByLabelText("Teléfono"), "3001234567");
    await userEvent.type(within(form).getByLabelText("Buscar producto"), "770MAR{enter}");
    await userEvent.clear(within(form).getByLabelText("Cantidad de Martillo 16 oz"));
    await userEvent.type(within(form).getByLabelText("Cantidad de Martillo 16 oz"), "3");
    expect(within(form).getAllByText("$ 84.000")).toHaveLength(2); // la línea y el total
    await userEvent.clear(within(form).getByLabelText("Vigencia (días)"));
    await userEvent.type(within(form).getByLabelText("Vigencia (días)"), "15");
    await userEvent.type(within(form).getByLabelText("Nota"), "Entrega en obra");
    await userEvent.click(within(form).getByRole("button", { name: "Guardar cotización" }));

    expect(await screen.findByRole("heading", { name: "COT-000046" })).toBeInTheDocument();
    const post = calls.find((c) => c.method === "POST")!.body as Record<string, unknown>;
    expect(post).toMatchObject({
      customer: null, customer_name: "Don Jorge", customer_phone: "3001234567", note: "Entrega en obra", valid_days: 15,
      lines: [{ product: 2, unit: "und", quantity: "3" }],
    });
    expect(typeof post.client_uuid).toBe("string");
  });

  it("busca por número, cliente o teléfono y filtra por estado", async () => {
    const calls = mockApi(vendor, {
      "GET /api/quotes/?status=VALID&q=COT-45": () => json([row]),
      "GET /api/quotes/?status=EXPIRED&q=COT-45": () => json([]),
    });
    renderPage();
    expect(await screen.findByRole("button", { name: "COT-000045" })).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Cotizaciones" })).toHaveTextContent(/Don Jorge.*3001234567.*andres.*920\.000/);
    await userEvent.type(screen.getByLabelText("Buscar cotización"), " COT-45 {enter}");
    await userEvent.click(screen.getByRole("button", { name: "Vencidas" }));
    expect(await screen.findByText("Nada por aquí.")).toBeInTheDocument();
    expect(calls.filter((c) => c.url.startsWith("/api/quotes/?")).map((c) => c.url)).toEqual([
      "/api/quotes/?status=VALID", "/api/quotes/?status=VALID&q=COT-45", "/api/quotes/?status=EXPIRED&q=COT-45",
    ]);
  });

  it("convierte una parte en pedido y muestra el código para la caja", async () => {
    // Después del pedido el servidor dice que del martillo quedan 4: lo precargado tiene que seguirlo.
    let current = detail;
    const calls = mockApi(vendor, {
      "GET /api/quotes/45/": () => json(current),
      "POST /api/quotes/45/order/": () => { current = { ...detail, lines: [{ ...detail.lines[0], in_orders: "6.000", remaining: "4.000" }, detail.lines[1]] }; return json(order, 201); },
    });
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "COT-000045" }));
    const section = await screen.findByRole("region", { name: "Convertir en pedido" });
    expect(within(section).getByLabelText("Cuánto se lleva de Martillo 16 oz")).toHaveValue("6"); // lo que queda
    expect(within(section).getByLabelText("Cuánto se lleva de Cable THHN")).toHaveValue("2");
    expect(screen.getByRole("list", { name: "Pedidos de esta cotización" })).toHaveTextContent(/4821.*112\.000.*por cobrar/);

    await userEvent.clear(within(section).getByLabelText("Cuánto se lleva de Martillo 16 oz"));
    await userEvent.type(within(section).getByLabelText("Cuánto se lleva de Martillo 16 oz"), "7");
    await userEvent.click(within(section).getByRole("button", { name: "Convertir en pedido" }));
    expect(within(section).getByRole("alert")).toHaveTextContent("MAR-16: quedan 6 und por convertir");

    await userEvent.clear(within(section).getByLabelText("Cuánto se lleva de Martillo 16 oz"));
    await userEvent.type(within(section).getByLabelText("Cuánto se lleva de Martillo 16 oz"), "2");
    await userEvent.clear(within(section).getByLabelText("Cuánto se lleva de Cable THHN"));
    await userEvent.type(within(section).getByLabelText("Cuánto se lleva de Cable THHN"), "0");
    await userEvent.click(within(section).getByRole("button", { name: "Convertir en pedido" }));
    expect(await screen.findByLabelText("Código del pedido")).toHaveTextContent("5932");
    expect(screen.getByRole("status")).toHaveTextContent(/precio cotizado.*Martillo 16 oz: queda bajo el mínimo/);
    const post = calls.find((c) => c.url.endsWith("/order/"))!.body as Record<string, unknown>;
    expect(post.lines).toEqual([{ quote_line: 1, quantity: "2" }]);
    expect(typeof post.client_uuid).toBe("string");

    await userEvent.click(screen.getByRole("button", { name: "Listo" }));
    expect(await screen.findByRole("region", { name: "Convertir en pedido" })).toBeInTheDocument(); // recarga el detalle
    await vi.waitFor(() => expect(screen.getByLabelText("Cuánto se lleva de Martillo 16 oz")).toHaveValue("4")); // lo que queda ahora, no lo de antes
    expect(calls.filter((c) => c.url === "/api/quotes/45/")).toHaveLength(2);
    await vi.waitFor(() => expect(calls.filter((c) => c.url === "/api/quotes/?status=VALID").length).toBeGreaterThanOrEqual(3)); // la lista también: al abrir, al convertir y al volver
  });

  it("todo en pedidos: no hay nada más que convertir", async () => {
    mockApi(vendor, {
      "GET /api/quotes/45/": () => json({ ...detail, lines: detail.lines.map((l) => ({ ...l, remaining: "0.000" })) }),
    });
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "COT-000045" }));
    expect(await screen.findByText(/Todo lo cotizado ya está en pedidos/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Convertir en pedido" })).not.toBeInTheDocument();
    expect(screen.getByLabelText("Cuánto se lleva de Martillo 16 oz")).toBeDisabled();
  });

  it("una vencida se duplica con los precios de hoy y se abre la nueva", async () => {
    const expired = { ...detail, status: "EXPIRED" as const, status_label: "Vencida", can_convert: false };
    const copy = { ...detail, id: 47, number: "COT-000047", duplicated_from: "COT-000045", orders: [] };
    const calls = mockApi(vendor, {
      "GET /api/quotes/45/": () => json(expired),
      "POST /api/quotes/45/duplicate/": () => json(copy, 201),
      "GET /api/quotes/47/": () => json(copy),
    });
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "COT-000045" }));
    expect(await screen.findByText(/Vencida: ya no se cobra al precio cotizado/)).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Convertir en pedido" })).not.toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Líneas de la cotización" })).toHaveTextContent(/Martillo 16 oz.*10 und/);
    expect(screen.queryByLabelText("Motivo de la anulación")).not.toBeInTheDocument(); // una vencida no se anula
    await userEvent.click(screen.getByRole("button", { name: "Duplicar con los precios de hoy" }));
    expect(await screen.findByRole("heading", { name: "COT-000047" })).toBeInTheDocument();
    expect(screen.getByText("duplicada de COT-000045")).toBeInTheDocument();
    expect(typeof (calls.find((c) => c.url.endsWith("/duplicate/"))!.body as { client_uuid: string }).client_uuid).toBe("string");
  });

  it("anular exige motivo y muestra el error del servidor", async () => {
    let quote: QuoteDetail = detail;
    const calls = mockApi(vendor, {
      "GET /api/quotes/45/": () => json(quote),
      "POST /api/quotes/45/void/": (body) => {
        if ((body as { note: string }).note === "Otra") return json({ detail: "Solo quien hizo la cotización o un supervisor puede anularla." }, 403);
        quote = { ...detail, status: "VOIDED", status_label: "Anulada", can_convert: false, voided_by: "andres", void_note: "Compró en otro lado" };
        return json(quote);
      },
    });
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "COT-000045" }));
    const voidButton = await screen.findByRole("button", { name: "Anular" });
    expect(voidButton).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Motivo de la anulación"), "Otra");
    await userEvent.click(voidButton);
    expect(await screen.findByText(/Solo quien hizo la cotización/)).toBeInTheDocument();
    await userEvent.clear(screen.getByLabelText("Motivo de la anulación"));
    await userEvent.type(screen.getByLabelText("Motivo de la anulación"), "Compró en otro lado");
    await userEvent.click(voidButton);
    expect(await screen.findByText("Anulada por andres: Compró en otro lado")).toBeInTheDocument();
    expect(calls.filter((c) => c.url.endsWith("/void/")).map((c) => c.body)).toEqual([{ note: "Otra" }, { note: "Compró en otro lado" }]);
  });

  it("quien solo ve (jefe de bodega) no cotiza, ni convierte, ni duplica", async () => {
    mockApi(["reports.view", "inventory.adjust"]);
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "COT-000045" }));
    expect(await screen.findByRole("table", { name: "Líneas de la cotización" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Nueva cotización" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Convertir en pedido" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Duplicar con los precios de hoy" })).not.toBeInTheDocument();
    expect(screen.getByLabelText("Motivo de la anulación")).toBeInTheDocument(); // anular sí puede
  });

  it("los errores al crear se ven", async () => {
    mockApi(vendor, { "POST /api/quotes/": () => json(["MAR-16 no está a la venta: no se puede cotizar."], 400) });
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "Nueva cotización" }));
    const form = screen.getByRole("form", { name: "Nueva cotización" });
    await userEvent.type(within(form).getByLabelText("A nombre de"), "Ana");
    await userEvent.type(within(form).getByLabelText("Buscar producto"), "770MAR{enter}");
    await userEvent.click(within(form).getByRole("button", { name: "Guardar cotización" }));
    expect(await within(form).findByRole("alert")).toHaveTextContent("MAR-16 no está a la venta");
  });
});
