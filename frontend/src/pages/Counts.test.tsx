import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { CountLine, PhysicalCount } from "../api";
import { AuthProvider } from "../auth";
import Counts from "./Counts";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

const line = (over: Partial<CountLine>): CountLine => ({
  id: 1, product: 1, sku: "X", name: "X", barcode: null, base_unit: "und", units: [], counted: null, counted_at: null,
  counted_by: null, marked_zero: false, expected: null, difference: null, value: null, ...over,
});
const hammer = line({ id: 11, product: 2, sku: "MAR-16", name: "Martillo 16 oz", barcode: "770MAR" });
const cable = line({ id: 12, product: 1, sku: "CAB-12", name: "Cable THHN", base_unit: "m", units: [{ unit: "rollo", factor: "100.000", barcode: "770ROLLO" }] });

const open: PhysicalCount = {
  id: 3, number: "CF-000003", warehouse: "PRAL", category: null, status: "OPEN", status_label: "Abierto", opened_by: "pedro",
  created_at: "2026-10-19T15:00:00Z", submitted_at: null, decided_by: null, decided_at: null, void_note: "", adjustment: null,
  total: 2, counted: 0, lines: [hammer, cable],
};

type Call = { method: string; url: string; body: unknown };

function mockApi(permissions: string[], routes: Record<string, (body: unknown) => Response> = {}) {
  const calls: Call[] = [];
  const me = { id: 1, username: "u", first_name: "", last_name: "", roles: [], permissions, must_change_password: false };
  const all: Record<string, (body: unknown) => Response> = {
    "GET /api/auth/csrf/": () => new Response(null, { status: 204 }),
    "GET /api/auth/me/": () => json(me),
    "GET /api/inventory/counts/?status=OPEN": () => json([{ ...open, lines: undefined }]),
    "GET /api/inventory/counts/3/": () => json(open),
    "GET /api/inventory/warehouses/": () => json([{ id: 1, code: "PRAL", name: "Bodega principal" }]),
    "GET /api/catalog/categories/": () => json([{ id: 4, name: "Eléctricos", products: 1 }]),
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

const renderPage = () => render(<AuthProvider><Counts /></AuthProvider>);
const counter = ["inventory.count"];
const boss = ["inventory.count", "inventory.adjust"];

describe("pantalla Conteos", () => {
  it("propone la bodega que recuerda este usuario y recuerda la que elige (spec 008)", async () => {
    localStorage.setItem("inventario.bodega.u", "2");
    const calls = mockApi(counter, {
      "GET /api/inventory/warehouses/": () => json([{ id: 1, code: "PRAL", name: "Bodega principal", is_default: true }, { id: 2, code: "LOC", name: "Local", is_default: false }]),
      "POST /api/inventory/counts/": () => json(open, 201),
    });
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "Nuevo conteo" }));
    const form = screen.getByRole("form", { name: "Nuevo conteo" });
    await vi.waitFor(() => expect(within(form).getByLabelText("Bodega")).toHaveValue("2"));
    await userEvent.selectOptions(within(form).getByLabelText("Bodega"), "1");
    expect(localStorage.getItem("inventario.bodega.u")).toBe("1");
    await userEvent.click(within(form).getByRole("button", { name: "Abrir conteo" }));
    await vi.waitFor(() => expect(calls.find((c) => c.method === "POST")?.body).toMatchObject({ warehouse: 1 }));
  });

  it("abre un conteo por categoría", async () => {
    const calls = mockApi(counter, {
      "POST /api/inventory/counts/": () => json({ ...open, id: 4, number: "CF-000004", category: "Eléctricos" }, 201),
      "GET /api/inventory/counts/4/": () => json({ ...open, id: 4, number: "CF-000004", category: "Eléctricos" }),
    });
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "Nuevo conteo" }));
    const form = screen.getByRole("form", { name: "Nuevo conteo" });
    await within(form).findByRole("option", { name: "Eléctricos" });
    await userEvent.selectOptions(within(form).getByLabelText("Qué contar"), "4");
    await userEvent.click(within(form).getByRole("button", { name: "Abrir conteo" }));
    expect(await screen.findByRole("heading", { name: "CF-000004" })).toBeInTheDocument();
    expect(calls.find((c) => c.method === "POST")!.body).toMatchObject({ warehouse: 1, category: 4 });
  });

  it("cuenta a ciegas: escanea el rollo, escribe y Enter guarda en esa unidad", async () => {
    const calls = mockApi(counter, {
      "PATCH /api/inventory/counts/3/lines/12/": () => json({ ...cable, counted: "200.000", counted_by: "pedro" }),
    });
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "CF-000003" }));
    const section = await screen.findByRole("region", { name: "Contar" });
    expect(within(section).getByRole("table", { name: "Productos a contar" })).not.toHaveTextContent(/esperado|sistema/i);
    await userEvent.type(within(section).getByLabelText("Escanear producto"), "770ROLLO{enter}");
    expect(within(section).getByLabelText("Unidad de Cable THHN")).toHaveValue("rollo");
    expect(within(section).getByLabelText("Cantidad de Cable THHN")).toHaveFocus();
    await userEvent.type(within(section).getByLabelText("Cantidad de Cable THHN"), "2{enter}");
    expect(await within(section).findByText("200 m")).toBeInTheDocument();
    expect(calls.find((c) => c.method === "PATCH")!.body).toEqual({ quantity: "2", unit: "rollo" });
    expect(screen.getByText(/1 de 2 contados/)).toBeInTheDocument();
    await vi.waitFor(() => expect(calls.filter((c) => c.url === "/api/inventory/counts/?status=OPEN")).toHaveLength(2)); // la lista se refresca

    await userEvent.type(within(section).getByLabelText("Escanear producto"), "999{enter}");
    expect(within(section).getByRole("alert")).toHaveTextContent('"999" no está en este conteo');
  });

  it("al escanear, el foco pasa a la cantidad en el acto aunque el filtro ocultara la fila", async () => {
    mockApi(counter);
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "CF-000003" }));
    const section = await screen.findByRole("region", { name: "Contar" });
    await userEvent.type(within(section).getByLabelText("Filtrar productos"), "martillo");
    const scan = within(section).getByLabelText("Escanear producto");
    fireEvent.change(scan, { target: { value: "770ROLLO" } });
    fireEvent.submit(scan);
    // sin esperar: lo siguiente que teclee la persona tiene que caer en la cantidad
    expect(within(section).getByLabelText("Cantidad de Cable THHN")).toHaveFocus();
    expect(within(section).getByLabelText("Filtrar productos")).toHaveValue("");
  });

  it("filtra, avisa si falta la cantidad y no envía sin nada contado", async () => {
    mockApi(counter);
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "CF-000003" }));
    const section = await screen.findByRole("region", { name: "Contar" });
    await userEvent.type(within(section).getByLabelText("Filtrar productos"), "martillo");
    expect(within(section).getAllByRole("row")).toHaveLength(2); // encabezado + martillo
    await userEvent.type(within(section).getByLabelText("Cantidad de Martillo 16 oz"), "x{enter}");
    expect(within(section).getByRole("alert")).toHaveTextContent("MAR-16: escribe cuánto hay");
    expect(within(section).getByRole("button", { name: "Terminar y enviar a aprobación" })).toBeDisabled(); // nada contado
  });

  it("quien no aprueba ve que está por aprobar, sin diferencias", async () => {
    mockApi(counter, { "GET /api/inventory/counts/3/": () => json({ ...open, status: "SUBMITTED", counted: 1 }) });
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "CF-000003" }));
    expect(await screen.findByText(/lo aprueba quien tiene permiso de ajustes/)).toBeInTheDocument();
    expect(screen.queryByRole("table", { name: "Diferencias" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Motivo de la anulación")).not.toBeInTheDocument();
  });

  it("el jefe ve diferencias, marca en 0 lo no contado y aprueba", async () => {
    const submitted = {
      ...open, status: "SUBMITTED" as const, counted: 1,
      lines: [{ ...hammer, counted: "7.000", expected: "10.000", difference: "-3.000", value: "-60000.00" }, cable],
    };
    const calls = mockApi(boss, {
      "GET /api/inventory/counts/3/": () => json(submitted),
      "POST /api/inventory/counts/3/approve/": () => json({ ...submitted, status: "APPROVED", adjustment: "AJ-000009", decided_by: "marta", decided_at: "2026-10-19T16:00:00Z" }),
    });
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "CF-000003" }));
    const review = await screen.findByRole("region", { name: "Aprobar conteo" });
    const differences = within(review).getByRole("table", { name: "Diferencias" });
    expect(differences).toHaveTextContent(/Martillo.*7.*10.*-3 und.*60\.000/);
    expect(differences).not.toHaveTextContent("Cable"); // lo no contado va aparte
    await userEvent.click(within(review).getByLabelText("Marcar Cable THHN en 0"));
    await userEvent.click(within(review).getByRole("button", { name: "Aprobar y ajustar diferencias" }));
    expect(await screen.findByText("Las diferencias se aplicaron con el ajuste AJ-000009.")).toBeInTheDocument();
    expect(calls.find((c) => c.url.endsWith("/approve/"))!.body).toEqual({ zero_uncounted: "all" }); // era el único sin contar
  });

  it("marcar algunos en 0 manda sus ids; anular exige motivo", async () => {
    const extra = line({ id: 13, sku: "TOR-1/4", name: "Tornillo" });
    const submitted = { ...open, status: "SUBMITTED" as const, counted: 1, lines: [{ ...hammer, counted: "10.000", expected: "10.000", difference: "0.000" }, cable, extra] };
    const calls = mockApi(boss, {
      "GET /api/inventory/counts/3/": () => json(submitted),
      "POST /api/inventory/counts/3/approve/": () => json({ ...submitted, status: "APPROVED" }),
      "POST /api/inventory/counts/3/void/": () => json({ ...submitted, status: "VOIDED", void_note: "Mal contado" }),
    });
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "CF-000003" }));
    const review = await screen.findByRole("region", { name: "Aprobar conteo" });
    await userEvent.click(within(review).getByLabelText("Marcar Tornillo en 0"));
    const voidButton = screen.getByRole("button", { name: "Anular conteo" });
    expect(voidButton).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Motivo de la anulación"), "Mal contado");
    await userEvent.click(within(review).getByRole("button", { name: "Aprobar y ajustar diferencias" }));
    await vi.waitFor(() => expect(calls.find((c) => c.url.endsWith("/approve/"))?.body).toEqual({ zero_uncounted: [13] }));
    expect(await screen.findByText("Sin diferencias: no hizo falta ajustar.")).toBeInTheDocument();
  });

  it("marcar todos en 0 y anular con motivo", async () => {
    const extra = line({ id: 13, sku: "TOR-1/4", name: "Tornillo" });
    const submitted = { ...open, status: "SUBMITTED" as const, counted: 1, lines: [{ ...hammer, counted: "12.000", expected: "10.000", difference: "2.000" }, cable, extra] };
    const calls = mockApi(boss, {
      "GET /api/inventory/counts/3/": () => json(submitted),
      "POST /api/inventory/counts/3/void/": () => json({ ...submitted, status: "VOIDED", void_note: "Mal contado" }),
    });
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "CF-000003" }));
    const review = await screen.findByRole("region", { name: "Aprobar conteo" });
    expect(within(review).getByRole("table", { name: "Diferencias" })).toHaveTextContent("+2 und"); // sobrante con signo
    await userEvent.click(within(review).getByLabelText(/Marcar todos en 0/));
    expect(within(review).getByLabelText("Marcar Tornillo en 0")).toBeChecked();
    expect(within(review).getByLabelText("Marcar Cable THHN en 0")).toBeChecked();
    await userEvent.click(within(review).getByLabelText(/Marcar todos en 0/));
    expect(within(review).getByLabelText("Marcar Tornillo en 0")).not.toBeChecked();
    await userEvent.type(screen.getByLabelText("Motivo de la anulación"), "Mal contado");
    await userEvent.click(screen.getByRole("button", { name: "Anular conteo" }));
    expect(await screen.findByText("Anulado: Mal contado")).toBeInTheDocument();
    expect(calls.find((c) => c.url.endsWith("/void/"))!.body).toEqual({ note: "Mal contado" });
    expect(screen.queryByRole("button", { name: "Anular conteo" })).not.toBeInTheDocument();
  });

  it("envía a aprobación cuando ya hay algo contado", async () => {
    const calls = mockApi(counter, {
      "GET /api/inventory/counts/3/": () => json({ ...open, counted: 1, lines: [{ ...hammer, counted: "4.000" }, cable] }),
      "POST /api/inventory/counts/3/submit/": () => json({ ...open, status: "SUBMITTED", counted: 1 }),
    });
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "CF-000003" }));
    const section = await screen.findByRole("region", { name: "Contar" });
    await userEvent.click(within(section).getByLabelText(/Solo sin contar/));
    expect(within(section).queryByText("Martillo 16 oz")).not.toBeInTheDocument();
    expect(within(section).getByText("Cable THHN")).toBeInTheDocument();
    await userEvent.click(within(section).getByRole("button", { name: "Terminar y enviar a aprobación" }));
    expect(await screen.findByText(/lo aprueba quien tiene permiso de ajustes/)).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST" && c.url.endsWith("/submit/"))).toBe(true);
  });

  it("los errores del servidor se ven", async () => {
    mockApi(counter, {
      "POST /api/inventory/counts/": () => json(["Ya hay un conteo abierto con esos productos (CF-000003: MAR-16…)."], 400),
    });
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "Nuevo conteo" }));
    const form = screen.getByRole("form", { name: "Nuevo conteo" });
    await within(form).findByRole("option", { name: "Bodega principal" });
    await userEvent.click(within(form).getByRole("button", { name: "Abrir conteo" }));
    expect(await within(form).findByRole("alert")).toHaveTextContent("Ya hay un conteo abierto");
  });
});
