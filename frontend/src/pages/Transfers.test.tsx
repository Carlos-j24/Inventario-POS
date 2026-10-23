import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Product, Transfer } from "../api";
import { AuthProvider } from "../auth";
import Transfers from "./Transfers";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

const hammer: Product = {
  id: 2, sku: "MAR-16", name: "Martillo 16 oz", category: "Herramientas", base_unit: "und", barcode: "770MAR",
  sale_price: "28000.00", tax_rate: "19", allows_fractions: false, min_stock: "5", units: [],
};
const cable: Product = { ...hammer, id: 1, sku: "CAB-12", name: "Cable THHN", base_unit: "m", barcode: null, allows_fractions: true, units: [{ unit: "rollo", factor: "100", barcode: null }] };

const done: Transfer = {
  id: 4, number: "TR-000004", client_uuid: "x", origin: "PRAL", destination: "LOC", note: "Para la vitrina",
  created_by: "pedro", created_at: "2026-10-19T15:00:00Z",
  lines: [{ id: 9, product: 1, sku: "CAB-12", name: "Cable THHN", unit: "rollo", quantity: "2.000", base_quantity: "200.000", base_unit: "m", value: null }],
};
const warehouses = [{ id: 1, code: "PRAL", name: "Bodega principal", is_default: true }, { id: 2, code: "LOC", name: "Local", is_default: false }];

type Call = { method: string; url: string; body: unknown };

function mockApi(routes: Record<string, (body: unknown) => Response> = {}) {
  const calls: Call[] = [];
  const me = { id: 1, username: "u", first_name: "", last_name: "", roles: [], permissions: ["inventory.transfer", "inventory.view"], must_change_password: false };
  const all: Record<string, (body: unknown) => Response> = {
    "GET /api/auth/csrf/": () => new Response(null, { status: 204 }),
    "GET /api/auth/me/": () => json(me),
    "GET /api/inventory/transfers/": () => json([done]),
    "GET /api/inventory/warehouses/": () => json(warehouses),
    "GET /api/catalog/products/": () => json([hammer, cable]),
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

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

const renderPage = () => render(<AuthProvider><Transfers /></AuthProvider>);

async function openForm() {
  await userEvent.click(await screen.findByRole("button", { name: "Nuevo traslado" }));
  const form = screen.getByRole("form", { name: "Nuevo traslado" });
  await within(form).findAllByRole("option", { name: "Local" });
  return form;
}

describe("pantalla Traslados", () => {
  it("traslada rollos de la bodega al local y lo muestra", async () => {
    const created = { ...done, id: 5, number: "TR-000005" };
    let list = [done];
    const calls = mockApi({
      "GET /api/inventory/transfers/": () => json(list),
      "POST /api/inventory/transfers/": () => { list = [created, ...list]; return json(created, 201); },
    });
    renderPage();
    const form = await openForm();
    expect(within(form).getByLabelText("Sale de")).toHaveValue("1");
    expect(within(form).getByLabelText("Entra a")).toHaveValue("2"); // la segunda bodega, ya elegida
    await userEvent.type(within(form).getByLabelText("Buscar producto"), "cable");
    await userEvent.click(await within(form).findByRole("button", { name: /Cable THHN/ }));
    await userEvent.selectOptions(within(form).getByLabelText("Unidad de Cable THHN"), "rollo");
    await userEvent.clear(within(form).getByLabelText("Cantidad de Cable THHN"));
    await userEvent.type(within(form).getByLabelText("Cantidad de Cable THHN"), "2");
    await userEvent.type(within(form).getByLabelText("Nota (opcional)"), "Para la vitrina");
    await userEvent.click(within(form).getByRole("button", { name: "Trasladar" }));

    expect(await screen.findByRole("heading", { name: "TR-000005" })).toBeInTheDocument();
    const post = calls.find((c) => c.method === "POST")!.body as Record<string, unknown>;
    expect(post).toMatchObject({ origin: 1, destination: 2, note: "Para la vitrina", lines: [{ product: 1, unit: "rollo", quantity: "2" }] });
    expect(typeof post.client_uuid).toBe("string");
    expect(screen.getByText(/De PRAL a LOC · pedro/)).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Líneas" })).toHaveTextContent(/2 rollo.*200 m/);
    expect(within(screen.getByRole("table", { name: "Traslados" })).getAllByRole("row")).toHaveLength(3); // la lista se refrescó
  });

  it("avisa antes de enviar y muestra el error del servidor", async () => {
    const calls = mockApi({
      "POST /api/inventory/transfers/": () => json(["Stock insuficiente de MAR-16 en PRAL: hay 1.000, se piden 3."], 400),
    });
    renderPage();
    const form = await openForm();
    await userEvent.click(within(form).getByRole("button", { name: "Trasladar" }));
    expect(within(form).getByRole("alert")).toHaveTextContent("Agrega al menos un producto");
    await userEvent.type(within(form).getByLabelText("Buscar producto"), "martillo");
    await userEvent.click(await within(form).findByRole("button", { name: /Martillo/ }));
    await userEvent.selectOptions(within(form).getByLabelText("Entra a"), "1");
    await userEvent.click(within(form).getByRole("button", { name: "Trasladar" }));
    expect(within(form).getByRole("alert")).toHaveTextContent("bodegas distintas");
    expect(calls.some((c) => c.method === "POST")).toBe(false);

    await userEvent.selectOptions(within(form).getByLabelText("Entra a"), "2");
    await userEvent.click(within(form).getByRole("button", { name: "Quitar Martillo 16 oz" }));
    await userEvent.type(within(form).getByLabelText("Buscar producto"), "martillo");
    await userEvent.click(await within(form).findByRole("button", { name: /Martillo/ }));
    await userEvent.clear(within(form).getByLabelText("Cantidad de Martillo 16 oz"));
    await userEvent.type(within(form).getByLabelText("Cantidad de Martillo 16 oz"), "3");
    await userEvent.click(within(form).getByRole("button", { name: "Trasladar" }));
    expect(await within(form).findByRole("alert")).toHaveTextContent("Stock insuficiente de MAR-16");
  });

  it("propone de la bodega que este usuario usa hacia la principal, y no cambia lo recordado", async () => {
    localStorage.setItem("inventario.bodega.u", "2"); // en Entradas eligió el Local
    mockApi({ "GET /api/inventory/warehouses/": () => json([...warehouses, { id: 3, code: "VIT", name: "Vitrina", is_default: false }]) });
    renderPage();
    const form = await openForm();
    await vi.waitFor(() => expect(within(form).getByLabelText("Sale de")).toHaveValue("2"));
    expect(within(form).getByLabelText("Entra a")).toHaveValue("1");
    await userEvent.selectOptions(within(form).getByLabelText("Sale de"), "3");
    expect(localStorage.getItem("inventario.bodega.u")).toBe("2"); // un traslado es la excepción
  });

  it("espera a saber quién es antes de proponer el origen", async () => {
    localStorage.setItem("inventario.bodega.u", "2");
    const me = { id: 1, username: "u", first_name: "", last_name: "", roles: [], permissions: ["inventory.transfer", "inventory.view"], must_change_password: false };
    const late = () => new Promise<Response>((resolve) => setTimeout(() => resolve(json(me)), 60)); // el usuario llega después que las bodegas
    mockApi({ "GET /api/auth/me/": late as unknown as () => Response });
    renderPage();
    const form = await openForm();
    await vi.waitFor(() => expect(within(form).getByLabelText("Sale de")).toHaveValue("2"));
    expect(within(form).getByLabelText("Entra a")).toHaveValue("1");
  });

  it("con una sola bodega avisa que hace falta otra", async () => {
    mockApi({ "GET /api/inventory/warehouses/": () => json([warehouses[0]]) });
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "Nuevo traslado" }));
    expect(await screen.findByText(/Solo hay una bodega activa/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Trasladar" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Elige de qué bodega sale y a cuál entra");
  });

  it("el valor solo aparece si el servidor lo manda (reports.costs)", async () => {
    mockApi({
      "GET /api/inventory/transfers/": () => json([{ ...done, lines: [{ ...done.lines[0], value: "360000.00" }] }]),
    });
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "TR-000004" }));
    const lines = screen.getByRole("table", { name: "Líneas" });
    expect(lines).toHaveTextContent(/Valor/);
    expect(lines).toHaveTextContent(/Total.*360\.000/);
  });

  it("sin valor no hay columna", async () => {
    mockApi();
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "TR-000004" }));
    expect(screen.getByRole("table", { name: "Líneas" })).not.toHaveTextContent(/Valor|Total/);
    expect(screen.getByText("Para la vitrina")).toBeInTheDocument();
  });
});
