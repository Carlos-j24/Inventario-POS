import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Product } from "../api";
import type { ContingencyBlock } from "../contingency";
import { Checkout } from "./Pos";

const hammer: Product = {
  id: 2, sku: "MAR-16", name: "Martillo 16 oz", category: "Herramientas", base_unit: "und",
  barcode: null, sale_price: "28000.00", tax_rate: "19", allows_fractions: false, min_stock: "5", units: [],
};

function respond(body: unknown, status: number) {
  return new Response(JSON.stringify(body), { status });
}

function mockFetch(response: unknown, status = 201) {
  const fn = vi.fn().mockResolvedValue(respond(response, status));
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => vi.unstubAllGlobals());

function setup(overrides: Record<string, unknown> = {}) {
  const props = {
    shiftId: 7,
    lines: [{ key: "a", product: hammer, unit: "und", quantity: 3 }],
    totalCents: 8400000,
    username: "laura",
    queue: vi.fn().mockResolvedValue(undefined),
    onCancel: () => {},
    onPaid: vi.fn(),
    onQueued: vi.fn(),
    ...overrides,
  };
  render(<Checkout {...props} />);
  return props;
}

const payExact = async () => {
  await userEvent.click(screen.getAllByRole("button", { name: "Exacto" })[0]); // efectivo exacto
  await userEvent.click(screen.getByRole("button", { name: "Confirmar pago" }));
};

describe("Checkout en línea", () => {
  it("envía pago mixto con el turno y un client_uuid, y muestra las vueltas", async () => {
    const fetch = mockFetch({ id: 1, number: "V-000001", total: "84000.00", payments: [] });
    const props = setup();

    await userEvent.type(screen.getByLabelText("Tarjeta"), "60000");
    await userEvent.type(screen.getByLabelText("Efectivo"), "30000");
    expect(screen.getByText(/Vueltas/)).toHaveTextContent("6.000");

    await userEvent.click(screen.getByRole("button", { name: "Confirmar pago" }));
    const body = JSON.parse(fetch.mock.calls[0][1].body);
    expect(body.shift).toBe(7);
    expect(body.client_uuid).toMatch(/^[0-9a-f-]{36}$/);
    expect(body.offline).toBeUndefined();
    expect(body.lines).toEqual([{ product: 2, unit: "und", quantity: "3" }]);
    expect(body.payments).toEqual([
      { method: "CASH", amount: "30000.00", reference: "" },
      { method: "CARD", amount: "60000.00", reference: "" },
    ]);
    expect(props.onPaid).toHaveBeenCalled();
    expect(props.queue).not.toHaveBeenCalled();
  });

  it("no deja confirmar si falta dinero", async () => {
    mockFetch({});
    setup();
    await userEvent.type(screen.getByLabelText("Efectivo"), "50000");
    expect(screen.getByText(/Faltan/)).toHaveTextContent("34.000");
    expect(screen.getByRole("button", { name: "Confirmar pago" })).toBeDisabled();
  });

  it("un error del servidor se muestra, no va a la cola y el reintento reutiliza el client_uuid", async () => {
    const fetch = vi.fn()
      .mockResolvedValueOnce(respond({ detail: "Falla interna" }, 500))
      .mockResolvedValueOnce(respond({ id: 1, number: "V-1", total: "84000", payments: [] }, 201));
    vi.stubGlobal("fetch", fetch);
    const props = setup();
    await payExact();
    expect(await screen.findByRole("alert")).toHaveTextContent("Falla interna");
    expect(props.queue).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Confirmar pago" }));
    const first = JSON.parse(fetch.mock.calls[0][1].body).client_uuid;
    const second = JSON.parse(fetch.mock.calls[1][1].body).client_uuid;
    expect(second).toBe(first);
  });

  it("un rechazo de validación (400) se muestra y no va a la cola", async () => {
    mockFetch({ detail: "Stock insuficiente" }, 400);
    const props = setup();
    await payExact();
    expect(await screen.findByRole("alert")).toHaveTextContent("Stock insuficiente");
    expect(props.queue).not.toHaveBeenCalled();
  });
});

describe("Checkout con cliente (spec 005)", () => {
  it("sin elegir cliente no manda customer; con cliente y factura, los manda", async () => {
    const client = {
      id: 5, id_type: "31", id_type_label: "NIT", id_number: "800197268", check_digit: "4", person_type: "1",
      name: "Constructora SAS", email: "", phone: "", address: "", city: "", tax_responsibilities: [], is_final_consumer: false,
    };
    const fetch = vi.fn((url: string, _init?: RequestInit) =>
      Promise.resolve(url.startsWith("/api/customers/") ? respond([client], 200) : respond({ id: 1, number: "V-1", total: "84000.00", subtotal: "0", tax: "0", payments: [] }, 201)),
    );
    vi.stubGlobal("fetch", fetch);
    setup();
    expect(screen.queryByLabelText(/Pedir factura/)).not.toBeInTheDocument(); // consumidor final: no hay factura
    await userEvent.click(screen.getByRole("button", { name: "Identificar cliente" }));
    await userEvent.type(screen.getByLabelText("Buscar cliente"), "800");
    await userEvent.click(await screen.findByRole("button", { name: /Constructora SAS/ }));
    await userEvent.click(screen.getByLabelText(/Pedir factura/));
    await payExact();
    const sale = fetch.mock.calls.find(([u]) => u === "/api/sales/")!;
    const body = JSON.parse(sale[1]!.body as string);
    expect([body.customer, body.invoice]).toEqual([5, true]);
  });
});

describe("Checkout sin conexión", () => {
  it("sin red guarda la venta en la cola como offline, con el precio cobrado y el mismo client_uuid", async () => {
    const fetch = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));
    vi.stubGlobal("fetch", fetch);
    const props = setup();
    await payExact();

    expect(props.queue).toHaveBeenCalledTimes(1);
    const item = props.queue.mock.calls[0][0];
    const tried = JSON.parse(fetch.mock.calls[0][1].body);
    expect(item.client_uuid).toBe(tried.client_uuid);
    expect(item.username).toBe("laura");
    expect(item.status).toBe("pending");
    expect(item.totalCents).toBe(8400000);
    expect(item.body.offline).toBe(true);
    expect(item.body.lines).toEqual([{ product: 2, unit: "und", quantity: "3", unit_price: "28000.00" }]);
    expect(props.onQueued).toHaveBeenCalledWith(item);
    expect(props.onPaid).not.toHaveBeenCalled();
  });

  it("numera el tiquete con el bloque de contingencia de la caja (spec 005)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const saved: Record<number, ContingencyBlock[]> = { 3: [{ prefix: "CT1", start: 1, end: 50, next: 7 }] };
    const blocks = { get: async (r: number) => structuredClone(saved[r]), set: async (r: number, b: ContingencyBlock[]) => { saved[r] = b; } };
    const props = setup({ registerId: 3, blocks });
    await payExact();
    const item = props.queue.mock.calls[0][0];
    expect((item.body as { contingency_number: number }).contingency_number).toBe(7);
    expect(item.contingencyCode).toBe("CT17");
    expect(saved[3][0].next).toBe(8);
  });

  it("guarda el tiquete de contingencia para imprimirlo sin servidor", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const saved: Record<number, ContingencyBlock[]> = { 3: [{ prefix: "CT1", start: 1, end: 50, next: 7 }] };
    const blocks = { get: async (r: number) => structuredClone(saved[r]), set: async (r: number, b: ContingencyBlock[]) => { saved[r] = b; } };
    const props = setup({ registerId: 3, registerCode: "CAJA3", blocks, business: { name: "Ferretería", trade_name: "", nit: "", address: "", city: "", phone: "", email: "", tax_regime: "" } });
    await payExact();
    const ticket = props.queue.mock.calls[0][0].ticket;
    expect([ticket.title, ticket.code, ticket.total, ticket.register, ticket.cashier, ticket.business.name]).toEqual(
      ["Documento de contingencia", "CT17", "84000.00", "CAJA3", "laura", "Ferretería"],
    );
  });

  it("sin bloque de contingencia la venta va igual a la cola, sin número", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const blocks = { get: async () => undefined, set: async () => {} };
    const props = setup({ registerId: 3, blocks });
    await payExact();
    const item = props.queue.mock.calls[0][0];
    expect("contingency_number" in item.body).toBe(false);
    expect(item.contingencyCode).toBeUndefined();
  });

  it("con el servidor caído (503) también va a la cola", async () => {
    mockFetch({}, 503);
    const props = setup();
    await payExact();
    expect(props.queue).toHaveBeenCalledTimes(1);
  });

  it("si no se puede guardar en el equipo, avisa que no entregue la mercancía", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const props = setup({ queue: vi.fn().mockRejectedValue(new Error("QuotaExceeded")) });
    await payExact();
    expect(await screen.findByRole("alert")).toHaveTextContent("No entregues la mercancía");
    expect(props.onQueued).not.toHaveBeenCalled();
  });
});

describe("Checkout de un pedido (spec 002)", () => {
  const order = {
    id: 9, code: 4193, business_date: "2026-10-16", status: "PENDING" as const, salesperson: "andres",
    total: "56000.00", created_at: "", sale_number: null, lines: [],
  };
  const orderLines = [{ key: "o", product: hammer, unit: "und", quantity: 1, order: { lineId: 12, max: 2, priceCents: 2700000 } }];

  it("envía order y order_lines, no líneas sueltas", async () => {
    const fetch = mockFetch({ id: 1, number: "V-000010", total: "27000.00", payments: [] });
    const props = setup({ order, lines: orderLines, totalCents: 2700000 });
    await payExact();
    const body = JSON.parse(fetch.mock.calls[0][1].body);
    expect(body.order).toBe(9);
    expect(body.order_lines).toEqual([{ order_line: 12, quantity: "1" }]);
    expect(body.lines).toBeUndefined();
    expect(body.payments).toEqual([{ method: "CASH", amount: "27000.00", reference: "" }]);
    expect(props.onPaid).toHaveBeenCalled();
  });

  it("una orden de taller va a nombre de su cliente si no se elige otro (spec 011)", async () => {
    const fetch = mockFetch({ id: 1, number: "V-000011", total: "27000.00", payments: [] });
    setup({ order: { ...order, work_order: { id: 5, number: "OT-000005", customer: "Jorge Ramírez" } }, lines: orderLines, totalCents: 2700000 });
    expect(screen.getByText(/Cliente:/)).toHaveTextContent("Cliente: Jorge Ramírez (de la orden)");
    await payExact();
    expect(JSON.parse(fetch.mock.calls[0][1].body).customer).toBeUndefined(); // el servidor pone el de la orden
  });

  it("un pedido de mostrador sigue siendo de consumidor final", () => {
    setup({ order, lines: orderLines, totalCents: 2700000 });
    expect(screen.getByText(/Cliente:/)).toHaveTextContent("Cliente: Consumidor final");
  });

  it("sin red no va a la cola: los pedidos se cobran con conexión", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const props = setup({ order, lines: orderLines, totalCents: 2700000 });
    await payExact();
    expect(await screen.findByRole("alert")).toHaveTextContent("los pedidos se cobran con red");
    expect(props.queue).not.toHaveBeenCalled();
    expect(props.onQueued).not.toHaveBeenCalled();
  });
});
