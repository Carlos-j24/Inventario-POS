import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { MaintenancePlan, MaintenanceRow, Product } from "../api";
import { AuthProvider } from "../auth";
import Maintenance from "./Maintenance";
import { todayIso } from "./Sales";

const DUE = "/api/workshop/maintenance/";
const PLANS = "/api/workshop/plans/";
const today = todayIso();
const plus = (days: number) => new Date(Date.parse(`${today}T12:00:00Z`) + days * 86_400_000).toISOString().slice(0, 10);

const oilPlan: MaintenancePlan = {
  id: 1, name: "Cambio de aceite", every_km: 3000, every_days: 90, products: [21],
  product_list: [{ id: 21, sku: "ACE-20W50", name: "Aceite 20W50" }], is_active: true,
};
const brakes: MaintenancePlan = { ...oilPlan, id: 2, name: "Revisión de frenos", every_km: null, every_days: 180, is_active: false };
const row = (over: Partial<MaintenanceRow> = {}): MaintenanceRow => ({
  id: 7, plan: { id: 1, name: "Cambio de aceite" }, status: "PENDING", due_date: plus(-3), due_mileage: 18420, due_on: plus(-3),
  by_km: false, estimated: false, daily_km: "50.0", note: "", source_order: "OT-000004", done_order: null, notices: [], closed_at: null,
  motorcycle: { id: 1, plate: "XYZ12A", vin: "", brand: "Bajaj", model: "Boxer CT 100", mileage: 15420, mileage_at: null },
  owner: { id: 7, name: "Jorge Ramírez", phone: "300 123 4567" }, ...over,
});
const product = (over: Partial<Product>): Product => ({
  id: 21, sku: "ACE-20W50", name: "Aceite 20W50", category: "", base_unit: "UND", barcode: null, sale_price: "32000.00",
  tax_rate: "19.00", allows_fractions: false, min_stock: "0", units: [], ...over,
});

type Handler = (body: Record<string, unknown> | undefined) => Response;
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

function mockApi(permissions: string[], routes: Record<string, Handler>) {
  const me = { id: 1, username: "diana", first_name: "Diana", last_name: "", roles: [], permissions, must_change_password: false, workshop_enabled: true };
  const all: Record<string, Handler> = {
    "GET /api/auth/csrf/": () => new Response(null, { status: 204 }),
    "GET /api/auth/me/": () => json(me),
    [`GET ${PLANS}`]: () => json([oilPlan, brakes]),
    "GET /api/invoicing/business/": () => json({ name: "Moto Repuestos y Lavadero Arias S.A.S.", trade_name: "Moto Repuestos Arias" }),
    "GET /api/catalog/products/": () => json([product({}), product({ id: 22, sku: "ACE-10W40", name: "Aceite 10W40" })]),
    ...routes,
  };
  const fn = vi.fn((url: string, init?: RequestInit) => {
    const key = `${init?.method ?? "GET"} ${url}`;
    const h = all[key];
    return h ? Promise.resolve(h(init?.body ? JSON.parse(String(init.body)) : undefined)) : Promise.reject(new Error(`no simulada: ${key}`));
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}
const bodies = (fetch: ReturnType<typeof mockApi>, key: string) =>
  fetch.mock.calls.filter(([u, i]) => `${i?.method ?? "GET"} ${u}` === key).map(([, i]) => (i?.body ? JSON.parse(String(i.body)) : undefined));
const RECEPTION = ["workshop.receive"];

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

const renderPage = () => render(<AuthProvider><Maintenance /></AuthProvider>);
const card = () => screen.getByRole("complementary");

async function openRow(routes: Record<string, Handler> = {}, rows = [row()]) {
  const fetch = mockApi(RECEPTION, { [`GET ${DUE}?`]: () => json(rows), ...routes });
  renderPage();
  await userEvent.click(await screen.findByRole("button", { name: "XYZ12A · Bajaj Boxer CT 100" }));
  return fetch;
}

describe("pantalla Mantenimientos: por vencer", () => {
  it("lista lo que vence con el dueño, el teléfono y cuándo; filtra por plan y muestra los avisados a pedido", async () => {
    const fetch = mockApi(RECEPTION, {
      [`GET ${DUE}?`]: () => json([row(), row({ id: 8, due_on: plus(2), by_km: true, estimated: true, motorcycle: { ...row().motorcycle, id: 2, plate: "ABC34D", brand: "Bajaj", model: "Pulsar" } })]),
      [`GET ${DUE}?plan=2`]: () => json([]),
      [`GET ${DUE}?plan=2&notified=1`]: () => json([row({ id: 9, status: "NOTIFIED", plan: { id: 2, name: "Revisión de frenos" } })]),
    });
    renderPage();
    const late = await screen.findByRole("row", { name: /XYZ12A/ });
    expect(late).toHaveTextContent("Jorge Ramírez 300 123 4567");
    expect(late).toHaveTextContent("Cambio de aceite");
    expect(late).toHaveTextContent("Venció hace 3 días");
    expect(late).toHaveTextContent("Pendiente");
    expect(screen.getByRole("row", { name: /ABC34D/ })).toHaveTextContent("Vence en 2 días por km (aprox.)");
    expect(screen.queryByRole("button", { name: "Planes" })).not.toBeInTheDocument(); // recepción no edita planes
    await userEvent.selectOptions(screen.getByLabelText("Plan"), "Revisión de frenos");
    expect(await screen.findByText("No hay mantenimientos por vencer esta semana.")).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText(/Ver también los avisados/));
    expect(await screen.findByRole("row", { name: /Revisión de frenos/ })).toHaveTextContent("Avisado");
    expect(fetch).toHaveBeenCalledWith(`${DUE}?plan=2&notified=1`, expect.anything());
  });

  it("el botón de WhatsApp abre wa.me con el mensaje; después se marca avisado", async () => {
    const told = row({ status: "NOTIFIED", notices: [{ channel: "WHATSAPP", user: "diana", at: "2026-10-30T15:00:00Z" }] });
    const fetch = await openRow({ [`POST ${DUE}7/notify/`]: () => json(told) });
    expect(card()).toHaveTextContent("Dueño: Jorge Ramírez · 300 123 4567");
    expect(card()).toHaveTextContent("a los 18.420 km");
    expect(card()).toHaveTextContent("anda unos 50 km al día");
    const link = await within(card()).findByRole("link", { name: "Escribir por WhatsApp" });
    const href = link.getAttribute("href")!;
    expect(href.startsWith("https://wa.me/573001234567?text=")).toBe(true);
    expect(decodeURIComponent(href.split("text=")[1])).toBe(
      "Hola, Jorge Ramírez. Le escribimos de Moto Repuestos Arias. A su moto XYZ12A · Bajaj Boxer CT 100 le toca cambio de aceite "
      + `desde el ${new Date(`${plus(-3)}T12:00:00`).toLocaleDateString("es-CO", { day: "numeric", month: "long" })}. ¿Cuándo la puede traer?`);
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    await userEvent.click(within(card()).getByRole("button", { name: "Avisado por WhatsApp" }));
    expect(bodies(fetch, `POST ${DUE}7/notify/`)).toEqual([{ channel: "WHATSAPP" }]);
    expect(await within(card()).findByRole("status")).toHaveTextContent("Quedó avisado por WhatsApp.");
    expect(within(card()).getByRole("list", { name: "Avisos" })).toHaveTextContent("por WhatsApp (diana)");
  });

  it("un fijo no tiene botón de WhatsApp: se avisa por llamada", async () => {
    const fetch = await openRow({ [`POST ${DUE}7/notify/`]: () => json(row({ status: "NOTIFIED" })) },
      [row({ owner: { id: 7, name: "Jorge Ramírez", phone: "608 435 1234" } })]);
    expect(within(card()).queryByRole("link", { name: "Escribir por WhatsApp" })).not.toBeInTheDocument();
    expect(card()).toHaveTextContent("El teléfono no es un celular: avisa por llamada.");
    await userEvent.click(within(card()).getByRole("button", { name: "Avisado por llamada" }));
    expect(bodies(fetch, `POST ${DUE}7/notify/`)).toEqual([{ channel: "PHONE" }]);
  });

  it("ajusta con fecha, km y una nota", async () => {
    const fetch = await openRow({ [`POST ${DUE}7/adjust/`]: () => json(row({ due_date: "2026-12-15", due_mileage: null, note: "Viene en diciembre" })) });
    await userEvent.click(within(card()).getByRole("button", { name: "Ajustar fecha o kilometraje" }));
    const form = within(card()).getByRole("form", { name: "Ajustar" });
    const save = within(form).getByRole("button", { name: "Guardar ajuste" });
    await userEvent.clear(within(form).getByLabelText("A los km"));
    await userEvent.type(within(form).getByLabelText("A los km"), "0");
    expect(form).toHaveTextContent("Los km van en números mayores que cero.");
    await userEvent.clear(within(form).getByLabelText("A los km"));
    expect(save).toBeDisabled(); // falta la nota
    const date = within(form).getByLabelText("Vence el");
    await userEvent.clear(date);
    await userEvent.type(date, "2026-12-15");
    await userEvent.type(within(form).getByLabelText("Por qué"), " Viene en diciembre ");
    await userEvent.click(save);
    expect(bodies(fetch, `POST ${DUE}7/adjust/`)).toEqual([{ due_date: "2026-12-15", due_mileage: null, note: "Viene en diciembre" }]);
    expect(await within(card()).findByRole("status")).toHaveTextContent("Recordatorio ajustado.");
    expect(card()).toHaveTextContent("Viene en diciembre");
  });

  it("descarta con una nota y muestra el error del servidor", async () => {
    let calls = 0;
    const fetch = await openRow({
      [`POST ${DUE}7/dismiss/`]: () => (++calls === 1 ? json({ detail: "Esto lo hace recepción del taller." }, 403)
        : json(row({ status: "DISMISSED", note: "Vendió la moto", closed_at: "2026-10-30T15:00:00Z" }))),
    });
    await userEvent.click(within(card()).getByRole("button", { name: "Descartar" }));
    const form = within(card()).getByRole("generic", { name: "Descartar" });
    expect(within(form).getByRole("button", { name: "Descartar recordatorio" })).toBeDisabled();
    await userEvent.type(within(form).getByLabelText("Por qué se descarta"), "Vendió la moto");
    await userEvent.click(within(form).getByRole("button", { name: "Descartar recordatorio" }));
    expect(await within(card()).findByRole("alert")).toHaveTextContent("Esto lo hace recepción del taller.");
    await userEvent.click(within(form).getByRole("button", { name: "Descartar recordatorio" }));
    expect(await within(card()).findByRole("status")).toHaveTextContent("Recordatorio descartado: sale de la lista.");
    expect(card()).toHaveTextContent("Este recordatorio está descartado.");
    expect(within(card()).queryByRole("button", { name: "Avisado por WhatsApp" })).not.toBeInTheDocument();
    expect(bodies(fetch, `POST ${DUE}7/dismiss/`)).toEqual([{ note: "Vendió la moto" }, { note: "Vendió la moto" }]);
  });
});

describe("pantalla Mantenimientos: planes", () => {
  it("quien maneja el catálogo solo ve los planes", async () => {
    mockApi(["catalog.edit"], {});
    renderPage();
    const row1 = await screen.findByRole("row", { name: /Cambio de aceite/ });
    expect(row1).toHaveTextContent("Cada 3.000 km o 90 días");
    expect(row1).toHaveTextContent("Aceite 20W50");
    expect(screen.getByRole("row", { name: /Revisión de frenos/ })).toHaveTextContent("inactivo");
    expect(screen.queryByText("Mantenimientos por vencer")).not.toBeInTheDocument();
  });

  it("con los dos permisos se cambia de pestaña", async () => {
    mockApi(["workshop.receive", "catalog.edit"], { [`GET ${DUE}?`]: () => json([]) });
    renderPage();
    expect(await screen.findByText("Mantenimientos por vencer")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Planes" }));
    expect(await screen.findByRole("heading", { name: "Planes de mantenimiento" })).toBeInTheDocument();
  });

  it("crea un plan con sus productos", async () => {
    const created = { ...oilPlan, id: 3, name: "Kit de arrastre", every_km: 15000, every_days: null, products: [22],
      product_list: [{ id: 22, sku: "ACE-10W40", name: "Aceite 10W40" }] };
    const fetch = mockApi(["catalog.edit"], { [`POST ${PLANS}`]: () => json(created, 201) });
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "Nuevo plan" }));
    const form = screen.getByRole("form", { name: "Plan" });
    const create = within(form).getByRole("button", { name: "Crear plan" });
    expect(create).toBeDisabled();
    expect(form).toHaveTextContent("Escribe el nombre del plan.");
    await userEvent.type(within(form).getByLabelText("Nombre"), "Kit de arrastre");
    await userEvent.type(within(form).getByLabelText("Cada cuántos km"), "15000");
    expect(form).toHaveTextContent("Elige al menos un producto o servicio que lo cumpla.");
    await userEvent.type(within(form).getByLabelText("Buscar producto"), "10W40");
    await userEvent.click(await within(form).findByRole("button", { name: /Aceite 10W40/ }));
    await userEvent.type(within(form).getByLabelText("Buscar producto"), "10W40");
    await userEvent.click(await within(form).findByRole("button", { name: /Aceite 10W40/ })); // no se repite
    expect(within(form).getByRole("list", { name: "Productos del plan" }).querySelectorAll("li")).toHaveLength(1);
    await userEvent.click(create);
    expect(bodies(fetch, `POST ${PLANS}`)).toEqual([{ name: "Kit de arrastre", every_km: 15000, every_days: null, products: [22], is_active: true }]);
    expect(await within(card()).findByRole("status")).toHaveTextContent("Plan creado.");
    expect(within(card()).getByRole("heading", { name: "Kit de arrastre" })).toBeInTheDocument();
  });

  it("cambia un plan: quita un producto y lo desactiva; muestra el error del servidor", async () => {
    let calls = 0;
    const fetch = mockApi(["catalog.edit"], {
      [`PATCH ${PLANS}1/`]: () => (++calls === 1 ? json({ name: ["Ya existe plan de mantenimiento con este nombre."] }, 400)
        : json({ ...oilPlan, is_active: false })),
    });
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "Cambio de aceite" }));
    const form = screen.getByRole("form", { name: "Plan" });
    expect(within(form).getByLabelText("Cada cuántos km")).toHaveValue("3000");
    await userEvent.click(within(form).getByRole("button", { name: "Quitar" }));
    expect(within(form).getByRole("button", { name: "Guardar plan" })).toBeDisabled();
    await userEvent.type(within(form).getByLabelText("Buscar producto"), "20W50");
    await userEvent.click(await within(form).findByRole("button", { name: /Aceite 20W50/ }));
    await userEvent.click(within(form).getByLabelText("Activo"));
    await userEvent.click(within(form).getByRole("button", { name: "Guardar plan" }));
    expect(await within(card()).findByRole("alert")).toHaveTextContent("name: Ya existe plan de mantenimiento con este nombre.");
    await userEvent.click(within(form).getByRole("button", { name: "Guardar plan" }));
    expect(await within(card()).findByRole("status")).toHaveTextContent("Plan guardado.");
    expect(bodies(fetch, `PATCH ${PLANS}1/`).at(-1)).toEqual({ name: "Cambio de aceite", every_km: 3000, every_days: 90, products: [21], is_active: false });
  });
});
