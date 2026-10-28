import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Adjustment, Product } from "../api";
import { AuthProvider } from "../auth";
import Adjustments from "./Adjustments";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

const hammer: Product = {
  id: 2, sku: "MAR-16", name: "Martillo 16 oz", category: "Herramientas", base_unit: "und", barcode: "770MAR",
  sale_price: "28000.00", tax_rate: "19", allows_fractions: false, min_stock: "5", units: [],
};
const cable: Product = { ...hammer, id: 1, sku: "CAB-12", name: "Cable THHN", base_unit: "m", barcode: null, allows_fractions: true, units: [{ unit: "rollo", factor: "100", barcode: null }] };

const pending: Adjustment = {
  id: 5, number: "AJ-000005", client_uuid: "x", warehouse: "PRAL", reason: "DAMAGE", reason_label: "Daño", note: "Se cayó del estante",
  status: "PENDING", status_label: "Pendiente de aprobación", requested_by: "pedro", created_at: "2026-10-19T15:00:00Z",
  decided_by: null, decided_at: null, rejection_note: "",
  lines: [{ id: 9, product: 1, sku: "CAB-12", name: "Cable THHN", unit: "rollo", quantity: "1.000", base_quantity: "-100.000", base_unit: "m", value: null }],
};

type Call = { method: string; url: string; body: unknown };

function mockApi(permissions: string[], routes: Record<string, (body: unknown) => Response> = {}) {
  const calls: Call[] = [];
  const me = { id: 1, username: "u", first_name: "", last_name: "", roles: [], permissions, must_change_password: false };
  const all: Record<string, (body: unknown) => Response> = {
    "GET /api/auth/csrf/": () => new Response(null, { status: 204 }),
    "GET /api/auth/me/": () => json(me),
    "GET /api/inventory/adjustments/?status=PENDING": () => json([pending]),
    "GET /api/inventory/adjustments/?status=APPROVED": () => json([]),
    "GET /api/inventory/warehouses/": () => json([{ id: 1, code: "PRAL", name: "Bodega principal" }]),
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

const renderPage = () => render(<AuthProvider><Adjustments /></AuthProvider>);
const helper = ["inventory.receive", "inventory.count"];
const boss = ["inventory.receive", "inventory.count", "inventory.adjust"];

describe("pantalla Ajustes", () => {
  it("no ofrece servicios: no tienen inventario (spec 010)", async () => {
    const wash = { ...hammer, id: 3, sku: "LAV-150", name: "Lavado moto", is_service: true };
    mockApi(helper, { "GET /api/catalog/products/": () => json([hammer, wash]) });
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "Nuevo ajuste" }));
    const form = screen.getByRole("form", { name: "Nuevo ajuste" });
    await within(form).findByRole("option", { name: "Bodega principal" });
    await userEvent.type(within(form).getByLabelText("Buscar producto"), "lavado");
    expect(within(form).queryByRole("button", { name: /Lavado moto/ })).not.toBeInTheDocument();
    await userEvent.clear(within(form).getByLabelText("Buscar producto"));
    await userEvent.type(within(form).getByLabelText("Buscar producto"), "martillo");
    expect(await within(form).findByRole("button", { name: /Martillo 16 oz/ })).toBeInTheDocument();
  });

  it("propone la bodega que recuerda este usuario y recuerda la que elige (spec 008)", async () => {
    localStorage.setItem("inventario.bodega.u", "2");
    mockApi(helper, { "GET /api/inventory/warehouses/": () => json([{ id: 1, code: "PRAL", name: "Bodega principal", is_default: true }, { id: 2, code: "LOC", name: "Local", is_default: false }]) });
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "Nuevo ajuste" }));
    const form = screen.getByRole("form", { name: "Nuevo ajuste" });
    await vi.waitFor(() => expect(within(form).getByLabelText("Bodega")).toHaveValue("2"));
    await userEvent.selectOptions(within(form).getByLabelText("Bodega"), "1");
    expect(localStorage.getItem("inventario.bodega.u")).toBe("1");
  });

  it("bodega reporta una baja en rollos y queda pendiente", async () => {
    const created = { ...pending, id: 6, number: "AJ-000006" };
    let list = [pending];
    const calls = mockApi(helper, {
      "GET /api/inventory/adjustments/?status=PENDING": () => json(list),
      "POST /api/inventory/adjustments/": () => { list = [created, ...list]; return json(created, 201); },
    });
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "Nuevo ajuste" }));
    const form = screen.getByRole("form", { name: "Nuevo ajuste" });
    await within(form).findByRole("option", { name: "Bodega principal" });
    await userEvent.type(within(form).getByLabelText("Buscar producto"), "cable");
    await userEvent.click(await within(form).findByRole("button", { name: /Cable THHN/ }));
    await userEvent.selectOptions(within(form).getByLabelText("Unidad de Cable THHN"), "rollo");
    expect(within(form).queryByLabelText("Sentido de Cable THHN")).not.toBeInTheDocument(); // daño: siempre sale
    await userEvent.click(within(form).getByRole("button", { name: "Enviar para aprobación" }));
    expect(await within(form).findByRole("alert")).toHaveTextContent("Escribe una nota");
    await userEvent.type(within(form).getByLabelText("Nota"), "Se mojó el rollo");
    await userEvent.click(within(form).getByRole("button", { name: "Enviar para aprobación" }));

    expect(await screen.findByRole("heading", { name: "AJ-000006" })).toBeInTheDocument();
    const post = calls.find((c) => c.method === "POST")!.body as Record<string, unknown>;
    expect(post).toMatchObject({ warehouse: 1, reason: "DAMAGE", note: "Se mojó el rollo", lines: [{ product: 1, unit: "rollo", quantity: "1", direction: "OUT" }] });
    expect(typeof post.client_uuid).toBe("string");
    expect(screen.getByText(/Lo aprueba quien tiene permiso de ajustes/)).toBeInTheDocument(); // bodega no aprueba
    expect(screen.queryByRole("button", { name: "Aprobar y aplicar" })).not.toBeInTheDocument();
  });

  it("error de registro deja elegir el sentido; sobrante pide costo", async () => {
    const calls = mockApi(boss, { "POST /api/inventory/adjustments/": () => json({ ...pending, id: 7 }, 201) });
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "Nuevo ajuste" }));
    const form = screen.getByRole("form", { name: "Nuevo ajuste" });
    await userEvent.selectOptions(within(form).getByLabelText("Motivo"), "RECORD_ERROR");
    await userEvent.type(within(form).getByLabelText("Buscar producto"), "770MAR{enter}"); // lector de código de barras
    await userEvent.selectOptions(within(form).getByLabelText("Sentido de Martillo 16 oz"), "IN");
    await userEvent.type(within(form).getByLabelText("Costo de Martillo 16 oz"), "20.000");
    await userEvent.type(within(form).getByLabelText("Nota"), "Entró sin registrar");
    await userEvent.click(within(form).getByRole("button", { name: "Enviar para aprobación" }));
    await vi.waitFor(() => expect(calls.find((c) => c.method === "POST")).toBeDefined());
    expect((calls.find((c) => c.method === "POST")!.body as { lines: unknown[] }).lines).toEqual([
      { product: 2, unit: "und", quantity: "1", direction: "IN", unit_cost: "20000.00" },
    ]);
  });

  it("el jefe aprueba; el rechazo exige motivo", async () => {
    const calls = mockApi(boss, {
      "POST /api/inventory/adjustments/5/approve/": () => json({ ...pending, status: "APPROVED" }),
      "POST /api/inventory/adjustments/5/reject/": () => json({ ...pending, status: "REJECTED" }),
    });
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "AJ-000005" }));
    const lines = screen.getByRole("table", { name: "Líneas" });
    expect(lines).toHaveTextContent(/Cable THHN.*−1 rollo.*100 m/);
    expect(within(lines).queryByText("Valor")).not.toBeInTheDocument(); // sin reports.costs
    const reject = screen.getByRole("button", { name: "Rechazar" });
    expect(reject).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Motivo del rechazo"), "Estaba en otro estante");
    await userEvent.click(reject);
    await userEvent.click(screen.getByRole("button", { name: "Aprobar y aplicar" }));
    await vi.waitFor(() => expect(calls.filter((c) => c.method === "POST").map((c) => [c.url, c.body])).toEqual([
      ["/api/inventory/adjustments/5/reject/", { note: "Estaba en otro estante" }],
      ["/api/inventory/adjustments/5/approve/", {}],
    ]));
  });

  it("con reports.costs muestra el valor y el total; los errores del servidor se ven", async () => {
    const valued = { ...pending, lines: [{ ...pending.lines[0], value: "-180000.00" }, { ...pending.lines[0], id: 10, unit: "m", quantity: "5.000", base_quantity: "-5.000", value: "-9000.00" }] };
    mockApi([...boss, "reports.costs"], {
      "GET /api/inventory/adjustments/?status=PENDING": () => json([valued]),
      "POST /api/inventory/adjustments/5/approve/": () => json(["Stock insuficiente de CAB-12 en PRAL: hay 50, se piden 100."], 400),
    });
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "AJ-000005" }));
    expect(screen.getByRole("table", { name: "Líneas" })).toHaveTextContent(/Valor.*180\.000.*9\.000.*Total.*189\.000/);
    await userEvent.click(screen.getByRole("button", { name: "Aprobar y aplicar" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Stock insuficiente");
  });

  it("los filtros cambian la consulta", async () => {
    const calls = mockApi(helper);
    renderPage();
    await screen.findByRole("button", { name: "AJ-000005" });
    await userEvent.click(screen.getByRole("button", { name: "Aprobados" }));
    expect(await screen.findByText("Nada por aquí.")).toBeInTheDocument();
    expect(calls.map((c) => c.url)).toContain("/api/inventory/adjustments/?status=APPROVED");
  });
});
