import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Product } from "../api";
import { AuthProvider } from "../auth";
import Receipts from "./Receipts";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

const oil: Product = {
  id: 1, sku: "ACE-20W50", name: "Aceite 20W50", category: "Lubricantes", base_unit: "und", barcode: null,
  sale_price: "30000.00", tax_rate: "19", allows_fractions: false, min_stock: "2", units: [],
};
const wash: Product = { ...oil, id: 2, sku: "LAV-150", name: "Lavado moto", category: "Lavadero", is_service: true };

function mockApi() {
  const me = { id: 1, username: "u", first_name: "", last_name: "", roles: [], permissions: ["inventory.receive"], must_change_password: false };
  const routes: Record<string, () => Response> = {
    "GET /api/auth/csrf/": () => new Response(null, { status: 204 }),
    "GET /api/auth/me/": () => json(me),
    "GET /api/inventory/warehouses/": () => json([{ id: 1, code: "PRAL", name: "Bodega principal", is_default: true }]),
    "GET /api/catalog/products/": () => json([oil, wash]),
  };
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    const route = routes[`${init?.method ?? "GET"} ${url}`];
    return route ? Promise.resolve(route()) : Promise.reject(new Error(`ruta no simulada: ${url}`));
  }));
}

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("pantalla Entradas", () => {
  it("no ofrece servicios: no entran a bodega (spec 010)", async () => {
    mockApi();
    render(<AuthProvider><Receipts /></AuthProvider>);
    await screen.findByRole("option", { name: "Bodega principal" });
    const search = screen.getByPlaceholderText("SKU o nombre…");
    await userEvent.type(search, "lavado");
    expect(screen.queryByRole("button", { name: /Lavado moto/ })).not.toBeInTheDocument();
    await userEvent.clear(search);
    await userEvent.type(search, "aceite");
    expect(await screen.findByRole("button", { name: /Aceite 20W50/ })).toBeInTheDocument();
  });
});
