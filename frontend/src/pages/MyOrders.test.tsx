import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Product, WorkOrderDetail, WorkOrderLine, WorkOrderRow } from "../api";
import { AuthProvider } from "../auth";
import MyOrders from "./MyOrders";

const URL = "/api/workshop/orders/";
const me = { id: 3, username: "carlos", first_name: "Carlos", last_name: "", roles: ["Mecánico"], permissions: ["workshop.repair"], must_change_password: false, workshop_enabled: true };
const row = (over: Partial<WorkOrderRow> = {}): WorkOrderRow => ({
  id: 5, number: "OT-000005", status: "IN_REPAIR", mileage_in: 15400, request: "Cambio de aceite y revisar frenos",
  received_at: "2026-10-28T15:00:00Z", updated_at: "2026-10-28T15:00:00Z",
  motorcycle: { id: 1, plate: "XYZ12A", vin: "", brand: "Bajaj", model: "Boxer CT 100" },
  customer: { id: 7, name: "Jorge Ramírez", phone: "3001234567" }, mechanic: { id: 3, username: "carlos", name: "Carlos" }, ...over,
});
const line = (over: Partial<WorkOrderLine> = {}): WorkOrderLine => ({
  id: 11, product: 21, sku: "ACE-20W50", name: "Aceite 20W50", is_service: false, quantity: "1.000", unit_price: "32000.00",
  total: "32000.00", approved: true, taken: false, returned: false, added_by: "carlos", created_at: "2026-10-28T16:00:00Z", ...over,
});
const labor = (over: Partial<WorkOrderLine> = {}) =>
  line({ id: 12, product: 22, sku: "MO-GEN", name: "Mano de obra", is_service: true, unit_price: "25000.00", total: "25000.00", ...over });
const detail = (over: Partial<WorkOrderDetail> = {}): WorkOrderDetail => ({
  ...row(), mileage_out: null, condition: "Rayón en el tanque", diagnosis: "", received_by: "diana", lines: [],
  charged_total: "0.00", pending_total: "0.00", approvals: [], events: [], till_order: null, sale: null, next_maintenance: [], ...over,
});
const product = (over: Partial<Product>): Product => ({
  id: 21, sku: "ACE-20W50", name: "Aceite 20W50", category: "", base_unit: "UND", barcode: null, sale_price: "32000.00",
  tax_rate: "19.00", allows_fractions: false, min_stock: "0", units: [], ...over,
});

type Handler = (body: Record<string, unknown> | undefined) => Response;
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

function mockApi(routes: Record<string, Handler>) {
  const all: Record<string, Handler> = {
    "GET /api/auth/csrf/": () => new Response(null, { status: 204 }),
    "GET /api/auth/me/": () => json(me),
    [`GET ${URL}?mechanic=3`]: () => json([row()]),
    "GET /api/catalog/products/": () => json([product({}), product({ id: 22, sku: "MO-GEN", name: "Mano de obra", sale_price: "20000.00", is_service: true })]),
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

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

async function openCard(order: WorkOrderDetail, routes: Record<string, Handler> = {}) {
  const fetch = mockApi({ [`GET ${URL}5/`]: () => json(order), ...routes });
  render(<AuthProvider><MyOrders /></AuthProvider>);
  await userEvent.click(await screen.findByRole("button", { name: "OT-000005" }));
  await screen.findByRole("heading", { name: "OT-000005 · XYZ12A · Bajaj Boxer CT 100" });
  return fetch;
}
const card = () => screen.getByRole("complementary");
const rowOf = (name: RegExp) => within(card()).getByRole("row", { name });

describe("pantalla Mis órdenes", () => {
  it("lista solo las asignadas a quien entró", async () => {
    const fetch = mockApi({});
    render(<AuthProvider><MyOrders /></AuthProvider>);
    const first = await screen.findByRole("row", { name: /OT-000005/ });
    expect(first).toHaveTextContent("XYZ12A · Bajaj Boxer CT 100");
    expect(first).toHaveTextContent("Cambio de aceite y revisar frenos");
    expect(first).toHaveTextContent("En reparación");
    expect(fetch.mock.calls.filter(([u]) => String(u).startsWith(URL)).map(([u]) => u)).toEqual([`${URL}?mechanic=3`]);
  });

  it("sin órdenes lo dice", async () => {
    mockApi({ [`GET ${URL}?mechanic=3`]: () => json([]) });
    render(<AuthProvider><MyOrders /></AuthProvider>);
    expect(await screen.findByText("No tienes órdenes abiertas.")).toBeInTheDocument();
  });

  it("escribe el diagnóstico y pide la aprobación", async () => {
    const received = detail({ status: "RECEIVED" });
    const fetch = await openCard(received, {
      [`POST ${URL}5/diagnose/`]: (b) => json({ ...received, diagnosis: b?.diagnosis }),
      [`POST ${URL}5/lines/`]: () => json({ ...received, diagnosis: "Aceite vencido", lines: [line({ approved: false })] }, 201),
      [`POST ${URL}5/send-for-approval/`]: () => json({ ...received, status: "AWAITING_APPROVAL", diagnosis: "Aceite vencido", lines: [line({ approved: false })] }),
    });
    expect(card()).toHaveTextContent("Llegó con 15.400 km");
    expect(card()).toHaveTextContent("Estado al llegar: Rayón en el tanque");
    expect(card()).not.toHaveTextContent("Jorge"); // lo del cliente es de recepción
    const save = within(card()).getByRole("button", { name: "Guardar diagnóstico" });
    expect(save).toBeDisabled();
    await userEvent.type(within(card()).getByLabelText("Diagnóstico"), "  Aceite vencido ");
    await userEvent.click(save);
    expect(bodies(fetch, `POST ${URL}5/diagnose/`)).toEqual([{ diagnosis: "Aceite vencido" }]);
    expect(await within(card()).findByRole("status")).toHaveTextContent("Diagnóstico guardado.");
    expect(within(card()).getByLabelText("Diagnóstico")).toHaveValue("Aceite vencido");
    expect(within(card()).getByRole("button", { name: "Guardar diagnóstico" })).toBeDisabled();
    expect(within(card()).queryByRole("button", { name: "Pedir aprobación" })).not.toBeInTheDocument(); // nada por aprobar
    expect(within(card()).queryByRole("button", { name: "Marcar lista" })).not.toBeInTheDocument();
    // el mecánico agrega sin poner precio
    await userEvent.type(within(card()).getByLabelText("Buscar producto"), "Mano");
    await userEvent.click(await within(card()).findByRole("button", { name: /Mano de obra.*servicio/ }));
    expect(within(card()).queryByLabelText("Precio de este trabajo")).not.toBeInTheDocument();
    await userEvent.click(within(card()).getByRole("button", { name: "Agregar" }));
    expect(bodies(fetch, `POST ${URL}5/lines/`)).toEqual([{ product: "22", quantity: "1" }]);
    expect(rowOf(/Aceite 20W50/)).toHaveTextContent("Por aprobar");
    expect(rowOf(/Aceite 20W50/)).not.toHaveTextContent("32.000"); // los precios son de recepción
    expect(card()).not.toHaveTextContent("Hay cambios sin aprobar"); // eso es para marcar lista, en reparación
    await userEvent.click(within(card()).getByRole("button", { name: "Pedir aprobación" }));
    expect(await within(card()).findByRole("status")).toHaveTextContent("Pedida la aprobación: recepción se la muestra al cliente.");
    expect(card()).toHaveTextContent("Esperando que el cliente apruebe: recepción lo registra.");
    expect(within(card()).queryByRole("button", { name: "Pedir aprobación" })).not.toBeInTheDocument();
    expect(within(card()).queryByRole("button", { name: "Sacar" })).not.toBeInTheDocument(); // sin aprobar no sale
  });

  it("saca y regresa repuestos aprobados; la mano de obra no sale de la bodega", async () => {
    const order = detail({ lines: [line(), labor()] });
    const fetch = await openCard(order, {
      [`POST ${URL}5/lines/11/take/`]: () => json({ ...order, lines: [line({ taken: true }), labor()] }),
      [`POST ${URL}5/lines/11/return/`]: () => json({ ...order, lines: [line({ taken: true, returned: true }), labor()] }),
    });
    expect(within(rowOf(/Mano de obra/)).queryByRole("button", { name: "Sacar" })).not.toBeInTheDocument();
    expect(rowOf(/Mano de obra/)).toHaveTextContent("Aprobada");
    await userEvent.click(within(rowOf(/Aceite 20W50/)).getByRole("button", { name: "Sacar" }));
    expect(await within(card()).findByRole("status")).toHaveTextContent("Aceite 20W50 salió de la bodega.");
    const oil = rowOf(/Aceite 20W50/);
    expect(oil).toHaveTextContent("En la moto");
    expect(within(oil).queryByRole("button", { name: "Sacar" })).not.toBeInTheDocument();
    expect(within(oil).queryByRole("button", { name: "Quitar" })).not.toBeInTheDocument();
    await userEvent.click(within(oil).getByRole("button", { name: "Regresar" }));
    expect(await within(card()).findByRole("status")).toHaveTextContent("Aceite 20W50 volvió a la bodega.");
    expect(rowOf(/Aceite 20W50/)).toHaveTextContent("Regresado");
    expect(within(rowOf(/Aceite 20W50/)).queryByRole("button", { name: "Regresar" })).not.toBeInTheDocument();
    expect(bodies(fetch, `POST ${URL}5/lines/11/take/`)).toEqual([{}]);
    expect(bodies(fetch, `POST ${URL}5/lines/11/return/`)).toEqual([{}]);
  });

  it("quita lo que no ha salido y muestra el error del servidor", async () => {
    const order = detail({ lines: [line()] });
    await openCard(order, {
      [`DELETE ${URL}5/lines/11/`]: () => json({ detail: "La orden OT-000005 no está asignada a ti." }, 403),
    });
    await userEvent.click(within(rowOf(/Aceite 20W50/)).getByRole("button", { name: "Quitar" }));
    expect(await within(card()).findByRole("alert")).toHaveTextContent("La orden OT-000005 no está asignada a ti.");
  });

  it("marca lista solo con todo aprobado y puesto, y dice qué falta", async () => {
    const pending = detail({ lines: [line({ taken: true }), labor({ approved: false })] });
    const fetch = await openCard(pending, {
      [`DELETE ${URL}5/lines/12/`]: () => json({ ...pending, lines: [line({ taken: true })] }),
    });
    expect(within(card()).getByRole("button", { name: "Marcar lista" })).toBeDisabled();
    expect(card()).toHaveTextContent("Hay cambios sin aprobar: que el cliente los apruebe o quítalos.");
    expect(card()).toHaveTextContent("Lo agregado después de aprobar no sale de la bodega hasta que el cliente lo apruebe.");
    expect(within(card()).getByRole("button", { name: "Pedir aprobación" })).toBeEnabled();
    await userEvent.click(within(rowOf(/Mano de obra/)).getByRole("button", { name: "Quitar" }));
    expect(bodies(fetch, `DELETE ${URL}5/lines/12/`)).toEqual([undefined]);
    expect(await within(card()).findByRole("status")).toHaveTextContent("Mano de obra quitado.");
    expect(within(card()).getByRole("button", { name: "Marcar lista" })).toBeEnabled();
    expect(card()).not.toHaveTextContent("Hay cambios sin aprobar");
    expect(within(card()).queryByRole("button", { name: "Pedir aprobación" })).not.toBeInTheDocument();
  });

  it("con todo aprobado y puesto, la marca lista", async () => {
    const order = detail({ lines: [line({ taken: true }), labor()] });
    const fetch = await openCard(order, {
      [`POST ${URL}5/ready/`]: () => json({ ...order, status: "READY" }),
    });
    expect(card()).not.toHaveTextContent("sácalo o quítalo");
    await userEvent.click(within(card()).getByRole("button", { name: "Marcar lista" }));
    expect(bodies(fetch, `POST ${URL}5/ready/`)).toEqual([{}]);
    expect(await within(card()).findByRole("status")).toHaveTextContent("Orden lista: recepción la cobra y la entrega.");
    expect(within(card()).getByText("Lista", { selector: ".badge" })).toBeInTheDocument();
    // lista: ya no se edita
    expect(within(card()).queryByRole("button", { name: "Marcar lista" })).not.toBeInTheDocument();
    expect(within(card()).queryByLabelText("Diagnóstico")).not.toBeInTheDocument();
    expect(within(card()).queryByLabelText("Buscar producto")).not.toBeInTheDocument();
    expect(within(card()).queryByRole("button", { name: "Regresar" })).not.toBeInTheDocument();
    expect(card()).toHaveTextContent("sin diagnóstico");
  });

  it("un repuesto aprobado que no ha salido no deja marcarla lista", async () => {
    await openCard(detail({ lines: [line(), labor()] }));
    expect(within(card()).getByRole("button", { name: "Marcar lista" })).toBeDisabled();
    expect(card()).toHaveTextContent("Aceite 20W50 está aprobado pero no ha salido de la bodega: sácalo o quítalo.");
  });
});
