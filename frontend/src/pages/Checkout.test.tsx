import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Product } from "../api";
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

  it("sin red no va a la cola: los pedidos se cobran con conexión", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const props = setup({ order, lines: orderLines, totalCents: 2700000 });
    await payExact();
    expect(await screen.findByRole("alert")).toHaveTextContent("los pedidos se cobran con red");
    expect(props.queue).not.toHaveBeenCalled();
    expect(props.onQueued).not.toHaveBeenCalled();
  });
});
