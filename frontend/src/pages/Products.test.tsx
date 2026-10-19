import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { AdminProduct } from "../api";
import { AuthProvider } from "../auth";
import Products, { productsQuery } from "./Products";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

const hammer: AdminProduct = {
  id: 2, sku: "MAR-16", name: "Martillo 16 oz", category: 3, category_name: "Herramientas", base_unit: "und",
  barcode: null, sale_price: "28000.00", tax_rate: "19", vat_excluded: false, allows_fractions: false,
  min_stock: "5.000", is_active: true, price_pending: false, has_movements: true, units: [],
};
const cable: AdminProduct = {
  ...hammer, id: 1, sku: "CAB-12", name: "Cable THHN calibre 12", category_name: "Eléctricos", category: 4, base_unit: "m",
  sale_price: "3200.00", allows_fractions: true, has_movements: false,
  units: [{ id: 7, unit: "rollo", factor: "100.000", barcode: "ROLLO-12", is_active: true, in_use: true }],
};
const pending: AdminProduct = { ...hammer, id: 9, sku: "DES-PH2", name: "Destornillador PH2", sale_price: "0.00", price_pending: true, is_active: false, has_movements: false };

type Call = { method: string; url: string; body: unknown };

function mockApi(permissions: string[], routes: Record<string, (body: unknown) => Response> = {}) {
  const calls: Call[] = [];
  const me = { id: 1, username: "u", first_name: "", last_name: "", roles: [], permissions, must_change_password: false };
  const base: Record<string, (body: unknown) => Response> = {
    "GET /api/auth/csrf/": () => new Response(null, { status: 204 }),
    "GET /api/auth/me/": () => json(me),
    "GET /api/catalog/admin/products/": () => json([cable, hammer, pending]),
    "GET /api/catalog/categories/": () => json([{ id: 3, name: "Herramientas", products: 1 }, { id: 4, name: "Eléctricos", products: 1 }]),
    "GET /api/catalog/units/": () => json([{ id: 1, code: "und", name: "Unidad" }, { id: 2, code: "m", name: "Metro" }, { id: 3, code: "rollo", name: "Rollo" }, { id: 4, code: "caja", name: "Caja" }]),
    "GET /api/catalog/admin/products/2/price-history/": () => json([{ old_price: "26000.00", new_price: "28000.00", user: "dueno", at: "2026-10-18T15:00:00Z" }]),
    "GET /api/catalog/admin/products/1/price-history/": () => json([]),
    "GET /api/catalog/admin/products/9/price-history/": () => json([]),
    ...routes,
  };
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    const body = init?.body ? JSON.parse(init.body as string) : undefined;
    calls.push({ method, url, body });
    const route = base[`${method} ${url}`] ?? (url.startsWith("/api/catalog/admin/products/?") ? base["GET /api/catalog/admin/products/"] : undefined);
    return route ? Promise.resolve(route(body)) : Promise.reject(new Error(`ruta no simulada: ${method} ${url}`));
  }));
  return calls;
}

afterEach(() => vi.unstubAllGlobals());

const owner = ["catalog.edit", "catalog.edit_prices"];
const warehouseBoss = ["catalog.edit"];
const renderPage = () => render(<AuthProvider><Products /></AuthProvider>);

describe("productsQuery", () => {
  it("arma la búsqueda", () => {
    expect(productsQuery("", "", "")).toBe("/api/catalog/admin/products/");
    expect(productsQuery(" mar ", "3", "0")).toBe("/api/catalog/admin/products/?q=mar&category=3&active=0");
  });
});

describe("pantalla Productos", () => {
  it("lista con precio, pendientes e inactivos, y busca", async () => {
    const calls = mockApi(owner);
    renderPage();
    const table = await screen.findByRole("table", { name: "Productos" });
    await within(table).findByText("MAR-16");
    expect(within(table).getByRole("row", { name: /MAR-16/ })).toHaveTextContent(/Herramientas.*28\.000/);
    expect(within(table).getByRole("row", { name: /DES-PH2/ })).toHaveTextContent(/—.*Pendiente de precio/);
    await userEvent.type(screen.getByLabelText("Buscar producto"), "cab");
    await userEvent.selectOptions(screen.getByLabelText("Estado"), "1");
    await vi.waitFor(() => expect(calls.map((c) => c.url)).toContain("/api/catalog/admin/products/?q=cab&active=1"));
  });

  it("el dueño cambia el precio y solo se manda lo que cambió", async () => {
    const calls = mockApi(owner, {
      "PATCH /api/catalog/admin/products/2/": (body) => json({ ...hammer, ...(body as object), sale_price: "29500.00" }),
    });
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "MAR-16" }));
    const form = screen.getByRole("form", { name: "Producto" });
    expect(within(form).getByLabelText("SKU")).toBeDisabled(); // tiene movimientos
    expect(within(form).getByLabelText("Unidad base")).toBeDisabled();
    expect(await screen.findByRole("region", { name: "Historial de precios" })).toHaveTextContent(/dueno.*26\.000.*28\.000/);
    const price = within(form).getByLabelText(/Precio de venta/);
    await userEvent.clear(price);
    await userEvent.type(price, "29.500");
    await userEvent.click(within(form).getByRole("button", { name: "Guardar cambios" }));
    expect(await within(form).findByRole("status")).toHaveTextContent("Cambios guardados.");
    expect(calls.find((c) => c.method === "PATCH")!.body).toEqual({ sale_price: "29500.00" });
  });

  it("el jefe de bodega no puede tocar precio ni IVA, y crea productos pendientes de precio", async () => {
    const created = { ...pending, id: 10, sku: "LLA-10", name: "Llave 10 mm" };
    let list = [cable, hammer, pending];
    const calls = mockApi(warehouseBoss, {
      "GET /api/catalog/admin/products/": () => json(list),
      "POST /api/catalog/admin/products/": () => { list = [...list, created]; return json(created, 201); },
      "GET /api/catalog/admin/products/10/price-history/": () => json([]),
    });
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "Nuevo producto" }));
    const form = screen.getByRole("form", { name: "Producto" });
    expect(within(form).getByLabelText(/Precio de venta/)).toBeDisabled();
    expect(within(form).getByLabelText("IVA")).toBeDisabled();
    await userEvent.type(within(form).getByLabelText("SKU"), "LLA-10");
    await userEvent.type(within(form).getByLabelText("Nombre"), "Llave 10 mm");
    await userEvent.selectOptions(within(form).getByLabelText("Categoría"), "3");
    await userEvent.click(within(form).getByRole("button", { name: "Crear producto" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Queda inactivo");
    expect(await screen.findByRole("heading", { name: "Llave 10 mm" })).toBeInTheDocument(); // queda abierto para seguir
    expect(screen.getByText(/Pendiente de precio: no se vende/)).toBeInTheDocument();
    const post = calls.find((c) => c.method === "POST")!.body as Record<string, unknown>;
    expect(post).toMatchObject({ sku: "LLA-10", name: "Llave 10 mm", category: 3, base_unit: "und" });
    expect(post).not.toHaveProperty("sale_price");
    expect(post).not.toHaveProperty("tax_rate");
  });

  it("muestra el error del servidor", async () => {
    mockApi(owner, {
      "PATCH /api/catalog/admin/products/1/": () => json({ barcode: ["El código de barras 770 ya está en otro producto o presentación."] }, 400),
    });
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "CAB-12" }));
    const form = screen.getByRole("form", { name: "Producto" });
    expect(within(form).getByLabelText("SKU")).not.toBeDisabled(); // sin movimientos
    await userEvent.type(within(form).getByLabelText("Código de barras"), "770");
    await userEvent.click(within(form).getByRole("button", { name: "Guardar cambios" }));
    expect(await within(form).findByRole("alert")).toHaveTextContent("ya está en otro producto");
  });

  it("presentaciones: desactivar una usada, no ofrecer borrarla, y agregar otra", async () => {
    const calls = mockApi(owner, {
      "PATCH /api/catalog/admin/units/7/": () => json({ ...cable.units[0], is_active: false }),
      "POST /api/catalog/admin/products/1/units/": () => json({ id: 8, unit: "caja", factor: "50.000", barcode: null, is_active: true, in_use: false }, 201),
    });
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "CAB-12" }));
    const section = screen.getByRole("region", { name: "Presentaciones" });
    expect(section).toHaveTextContent(/1 rollo = 100 m.*ROLLO-12/);
    expect(within(section).queryByRole("button", { name: "Borrar" })).not.toBeInTheDocument(); // ya se usó
    await userEvent.click(within(section).getByRole("button", { name: "Desactivar" }));
    // la unidad base y las que ya tiene no se ofrecen
    const options = within(within(section).getByLabelText("Unidad de la presentación")).getAllByRole("option").map((o) => o.textContent);
    expect(options).toEqual(["Unidad…", "Unidad (und)", "Caja (caja)"]);
    const add = within(section).getByRole("button", { name: "Agregar" });
    expect(add).toBeDisabled();
    await userEvent.selectOptions(within(section).getByLabelText("Unidad de la presentación"), "caja");
    await userEvent.type(within(section).getByLabelText("Factor"), "50");
    await userEvent.click(add);
    await vi.waitFor(() => expect(calls.find((c) => c.method === "POST")?.body).toEqual({ unit: "caja", factor: "50", barcode: null }));
    expect(calls.find((c) => c.method === "PATCH")!.body).toEqual({ is_active: false });
  });
});
