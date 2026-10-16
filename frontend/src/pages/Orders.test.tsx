import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Order, Product } from "../api";
import Orders from "./Orders";

const hammer: Product = {
  id: 2, sku: "MAR-16", name: "Martillo 16 oz", category: "Herramientas", base_unit: "und",
  barcode: "7703", sale_price: "28000.00", tax_rate: "19", allows_fractions: false, min_stock: "5", units: [],
};

const pendingOrder: Order = {
  id: 9, code: 1234, business_date: "2026-10-16", status: "PENDING", salesperson: "andres",
  total: "28000.00", created_at: "2026-10-16T15:00:00Z", sale_number: null,
  lines: [{ id: 1, product: 2, sku: "MAR-16", name: "Martillo 16 oz", unit: "und", quantity: "1.000", unit_price: "28000.00", total: "28000.00" }],
};

type Handler = (body: unknown) => Response | Promise<Response>;

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status });
}

/** fetch falso por "MÉTODO url". Devuelve el mock para revisar las llamadas. */
function mockApi(routes: Record<string, Handler>) {
  const fn = vi.fn((url: string, init?: RequestInit) => {
    const key = `${init?.method ?? "GET"} ${url}`;
    const handler = routes[key];
    if (!handler) return Promise.reject(new Error(`ruta no simulada: ${key}`));
    return Promise.resolve(handler(init?.body ? JSON.parse(String(init.body)) : undefined));
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

const bodiesOf = (fetch: ReturnType<typeof mockApi>, key: string) =>
  fetch.mock.calls
    .filter(([url, init]) => `${init?.method ?? "GET"} ${url}` === key)
    .map(([, init]) => JSON.parse(String(init?.body)));

afterEach(() => vi.unstubAllGlobals());

async function addHammer() {
  await userEvent.type(await screen.findByLabelText("Buscar producto"), "7703{Enter}");
}

describe("pantalla Pedidos", () => {
  it("arma el pedido con el lector, lo crea y muestra el código y los avisos de stock", async () => {
    const fetch = mockApi({
      "GET /api/catalog/products/": () => json([hammer]),
      "GET /api/orders/?mine=1": () => json([]),
      "POST /api/orders/": () => json({
        ...pendingOrder, code: 4821, total: "56000.00",
        warnings: [{ sku: "MAR-16", name: "Martillo 16 oz", kind: "sin_existencias", available: "1.000" }],
      }, 201),
    });
    render(<Orders />);
    await addHammer();
    await addHammer(); // el segundo escaneo suma 1
    expect(screen.getByLabelText("Cantidad de Martillo 16 oz")).toHaveValue(2);

    await userEvent.click(screen.getByRole("button", { name: "Crear pedido" }));
    expect(await screen.findByLabelText("Código del pedido")).toHaveTextContent("4821");
    expect(screen.getByText(/hay 1, no alcanza/)).toBeInTheDocument();

    const [body] = bodiesOf(fetch, "POST /api/orders/");
    expect(body.client_uuid).toMatch(/^[0-9a-f-]{36}$/);
    expect(body.lines).toEqual([{ product: 2, unit: "und", quantity: "2" }]);
  });

  it("sin conexión avisa que los pedidos necesitan red y el reintento usa el mismo client_uuid", async () => {
    let attempts = 0;
    const fetch = mockApi({
      "GET /api/catalog/products/": () => json([hammer]),
      "GET /api/orders/?mine=1": () => json([]),
      "POST /api/orders/": () => {
        attempts++;
        if (attempts === 1) throw new TypeError("Failed to fetch");
        return json({ ...pendingOrder, code: 4821 }, 201);
      },
    });
    render(<Orders />);
    await addHammer();
    await userEvent.click(screen.getByRole("button", { name: "Crear pedido" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("necesitan red");

    await userEvent.click(screen.getByRole("button", { name: "Crear pedido" }));
    expect(await screen.findByLabelText("Código del pedido")).toHaveTextContent("4821");
    const [first, second] = bodiesOf(fetch, "POST /api/orders/");
    expect(second.client_uuid).toBe(first.client_uuid);
  });

  it("cada pedido nuevo lleva su propio client_uuid (si no, el servidor devolvería el anterior)", async () => {
    let code = 4000;
    const fetch = mockApi({
      "GET /api/catalog/products/": () => json([hammer]),
      "GET /api/orders/?mine=1": () => json([]),
      "POST /api/orders/": () => json({ ...pendingOrder, code: ++code }, 201),
    });
    render(<Orders />);
    await addHammer();
    await userEvent.click(screen.getByRole("button", { name: "Crear pedido" }));
    await userEvent.click(await screen.findByRole("button", { name: "Nuevo pedido" }));
    await addHammer();
    await userEvent.click(screen.getByRole("button", { name: "Crear pedido" }));
    expect(await screen.findByLabelText("Código del pedido")).toHaveTextContent("4002");

    const [first, second] = bodiesOf(fetch, "POST /api/orders/");
    expect(second.client_uuid).not.toBe(first.client_uuid);
  });

  it("no deja crear un pedido con cantidades inválidas", async () => {
    mockApi({
      "GET /api/catalog/products/": () => json([hammer]),
      "GET /api/orders/?mine=1": () => json([]),
    });
    render(<Orders />);
    await addHammer();
    const qty = screen.getByLabelText("Cantidad de Martillo 16 oz");
    await userEvent.clear(qty);
    await userEvent.type(qty, "0.5");
    expect(screen.getByText(/no se vende fraccionado/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Crear pedido" })).toBeDisabled();
  });

  it("lista mis pendientes y cancela uno con confirmación en la misma pantalla", async () => {
    let cancelled = false;
    const fetch = mockApi({
      "GET /api/catalog/products/": () => json([hammer]),
      "GET /api/orders/?mine=1": () => json(cancelled ? [] : [pendingOrder]),
      "POST /api/orders/9/cancel/": () => { cancelled = true; return json({ ...pendingOrder, status: "CANCELLED" }); },
    });
    render(<Orders />);
    expect(await screen.findByText("1234")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Cancelar pedido 1234" }));
    expect(fetch.mock.calls.some(([url]) => url === "/api/orders/9/cancel/")).toBe(false); // aún no
    await userEvent.click(screen.getByRole("button", { name: "Sí, cancelar" }));

    await waitFor(() => expect(screen.queryByText("1234")).not.toBeInTheDocument());
    expect(screen.getByText("Ninguno.")).toBeInTheDocument();
  });
});
