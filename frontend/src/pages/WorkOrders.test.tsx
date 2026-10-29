import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Business, Motorcycle, Product, WorkOrderDetail, WorkOrderLine, WorkOrderRow } from "../api";
import WorkOrders from "./WorkOrders";

const URL = "/api/workshop/orders/";
const carlos = { id: 3, username: "carlos", name: "Carlos Gómez" };
const pablo = { id: 4, username: "pablo", name: "Pablo" };
const row = (over: Partial<WorkOrderRow> = {}): WorkOrderRow => ({
  id: 5, number: "OT-000005", status: "RECEIVED", mileage_in: 15400, request: "Cambio de aceite y revisar frenos",
  received_at: "2026-10-28T15:00:00Z", updated_at: "2026-10-28T15:00:00Z",
  motorcycle: { id: 1, plate: "XYZ12A", vin: "", brand: "Bajaj", model: "Boxer CT 100" },
  customer: { id: 7, name: "Jorge Ramírez", phone: "3001234567" }, mechanic: carlos, ...over,
});
const line = (over: Partial<WorkOrderLine> = {}): WorkOrderLine => ({
  id: 11, product: 21, sku: "ACE-20W50", name: "Aceite 20W50", is_service: false, quantity: "1.000", unit_price: "32000.00",
  total: "32000.00", approved: false, taken: false, returned: false, added_by: "carlos", created_at: "2026-10-28T16:00:00Z", ...over,
});
const labor = (over: Partial<WorkOrderLine> = {}) =>
  line({ id: 12, product: 22, sku: "MO-GEN", name: "Mano de obra", is_service: true, unit_price: "0.00", total: "0.00", ...over });
const detail = (over: Partial<WorkOrderDetail> = {}): WorkOrderDetail => ({
  ...row(), mileage_out: null, condition: "Rayón en el tanque, deja el casco", diagnosis: "", received_by: "diana",
  lines: [], charged_total: "0.00", pending_total: "0.00", approvals: [],
  events: [{ status: "RECEIVED", note: "", user: "diana", at: "2026-10-28T15:00:00Z" }], till_order: null, sale: null, ...over,
});
const moto: Motorcycle = {
  id: 1, plate: "XYZ12A", vin: "", brand: "Bajaj", model: "Boxer CT 100", year: 2019, displacement_cc: 100, color: "", notes: "",
  is_active: true, mileage: 15200, mileage_at: null, created_at: "2026-10-20T15:00:00Z", updated_at: "2026-10-20T15:00:00Z",
  owner: { id: 7, name: "Jorge Ramírez", id_type: "13", id_number: "79123456", check_digit: "", phone: "3001234567" },
};
const product = (over: Partial<Product>): Product => ({
  id: 21, sku: "ACE-20W50", name: "Aceite 20W50", category: "", base_unit: "UND", barcode: null, sale_price: "32000.00",
  tax_rate: "19.00", allows_fractions: false, min_stock: "0", units: [], ...over,
});
const business: Business = {
  name: "Moto Repuestos y Lavadero Arias", trade_name: "", nit: "900123456-7", address: "Cra 1", city: "Florencia",
  phone: "3100000000", email: "", tax_regime: "",
};

type Handler = (body: Record<string, unknown> | undefined) => Response;
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

function mockApi(routes: Record<string, Handler>) {
  const fn = vi.fn((url: string, init?: RequestInit) => {
    const key = `${init?.method ?? "GET"} ${url}`;
    const h = routes[key];
    return h ? Promise.resolve(h(init?.body ? JSON.parse(String(init.body)) : undefined)) : Promise.reject(new Error(`no simulada: ${key}`));
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}
const bodies = (fetch: ReturnType<typeof mockApi>, key: string) =>
  fetch.mock.calls.filter(([u, i]) => `${i?.method ?? "GET"} ${u}` === key).map(([, i]) => (i?.body ? JSON.parse(String(i.body)) : undefined));
const base = {
  [`GET ${URL}`]: () => json([row()]),
  [`GET ${URL}mechanics/`]: () => json([carlos, pablo]),
  "GET /api/catalog/products/": () => json([product({}), product({ id: 22, sku: "MO-GEN", name: "Mano de obra", sale_price: "0.00", is_service: true })]),
};

afterEach(() => vi.unstubAllGlobals());

async function openCard(order: WorkOrderDetail, routes: Record<string, Handler> = {}) {
  const fetch = mockApi({ ...base, [`GET ${URL}5/`]: () => json(order), ...routes });
  render(<WorkOrders />);
  await userEvent.click(await screen.findByRole("button", { name: "OT-000005" }));
  await screen.findByRole("heading", { name: "OT-000005 · XYZ12A · Bajaj Boxer CT 100" });
  return fetch;
}
const card = () => screen.getByRole("complementary");

describe("pantalla Órdenes", () => {
  it("lista las abiertas, filtra por estado y busca por placa o cliente", async () => {
    const fetch = mockApi({
      ...base,
      [`GET ${URL}`]: () => json([row(), row({ id: 6, number: "OT-000006", status: "READY", mechanic: null,
        motorcycle: { id: 2, plate: "ABC12D", vin: "", brand: "Honda", model: "CB 125" }, customer: { id: 8, name: "Ana Pérez", phone: "3109998877" } })]),
      [`GET ${URL}?status=CANCELLED`]: () => json([]),
    });
    render(<WorkOrders />);
    const first = await screen.findByRole("row", { name: /OT-000005/ });
    expect(first).toHaveTextContent("XYZ12A · Bajaj Boxer CT 100");
    expect(first).toHaveTextContent("Jorge Ramírez 3001234567");
    expect(first).toHaveTextContent("Carlos Gómez");
    expect(first).toHaveTextContent("Recibida");
    expect(screen.getByRole("row", { name: /OT-000006/ })).toHaveTextContent("Sin asignarLista");
    await userEvent.type(screen.getByLabelText("Buscar orden"), "abc-12");
    expect(screen.queryByRole("row", { name: /OT-000005/ })).not.toBeInTheDocument();
    expect(screen.getByRole("row", { name: /OT-000006/ })).toBeInTheDocument();
    await userEvent.clear(screen.getByLabelText("Buscar orden"));
    await userEvent.type(screen.getByLabelText("Buscar orden"), "jorge");
    expect(screen.getAllByRole("row")).toHaveLength(2); // encabezado + la de Jorge
    expect(screen.getByRole("row", { name: /OT-000005/ })).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Buscar orden"), "zzz");
    expect(screen.getByText("Ninguna orden coincide.")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Estado"), "CANCELLED");
    expect(await screen.findByText("Ninguna orden coincide.")).toBeInTheDocument();
    await userEvent.clear(screen.getByLabelText("Buscar orden"));
    expect(screen.getByText("No hay órdenes en este estado.")).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith(`${URL}?status=CANCELLED`, expect.anything());
  });

  it("recibe una moto buscándola", async () => {
    const fetch = mockApi({
      ...base,
      "GET /api/workshop/motorcycles/?q=xyz": () => json([moto]),
      [`POST ${URL}`]: () => json(detail(), 201),
      [`GET ${URL}5/`]: () => json(detail()),
    });
    render(<WorkOrders />);
    await screen.findByRole("row", { name: /OT-000005/ });
    await userEvent.click(screen.getByRole("button", { name: "Recibir moto" }));
    await userEvent.type(screen.getByLabelText("Buscar moto"), "xyz");
    await userEvent.click(await screen.findByRole("button", { name: "XYZ12A · Bajaj Boxer CT 100" }));
    const form = screen.getByRole("form", { name: "Recibir moto" });
    const open = within(form).getByRole("button", { name: "Abrir orden" });
    expect(open).toBeDisabled();
    await userEvent.type(within(form).getByLabelText("Kilometraje de llegada"), "15100");
    expect(within(form).getByText("El kilometraje es menor que el que tenía: explica por qué.")).toBeInTheDocument();
    await userEvent.clear(within(form).getByLabelText("Kilometraje de llegada"));
    await userEvent.type(within(form).getByLabelText("Kilometraje de llegada"), "15400");
    expect(within(form).queryByLabelText("Por qué baja el kilometraje")).not.toBeInTheDocument();
    await userEvent.type(within(form).getByLabelText("Qué pide el cliente"), "Cambio de aceite y revisar frenos");
    await userEvent.type(within(form).getByLabelText("Estado en que llega"), "Rayón en el tanque, deja el casco");
    await userEvent.selectOptions(await within(form).findByLabelText("Mecánico"), "Carlos Gómez");
    await userEvent.click(open);
    expect(bodies(fetch, `POST ${URL}`)).toEqual([{
      motorcycle: 1, mileage: 15400, mileage_note: "", request: "Cambio de aceite y revisar frenos",
      condition: "Rayón en el tanque, deja el casco", mechanic: 3,
    }]);
    expect(await screen.findByRole("heading", { name: "OT-000005 · XYZ12A · Bajaj Boxer CT 100" })).toBeInTheDocument();
  });

  it("muestra el error del servidor al recibir y, si no encuentra la moto, manda a registrarla", async () => {
    mockApi({
      ...base,
      "GET /api/workshop/motorcycles/?q=xyz": () => json([moto]),
      "GET /api/workshop/motorcycles/?q=nada": () => json([]),
      [`POST ${URL}`]: () => json(["La moto ya tiene una orden de trabajo abierta."], 400),
    });
    render(<WorkOrders />);
    await userEvent.click(await screen.findByRole("button", { name: "Recibir moto" }));
    await userEvent.type(screen.getByLabelText("Buscar moto"), "nada");
    expect(await screen.findByText(/Si es nueva, regístrala primero en Motos/)).toBeInTheDocument();
    await userEvent.clear(screen.getByLabelText("Buscar moto"));
    await userEvent.type(screen.getByLabelText("Buscar moto"), "xyz");
    await userEvent.click(await screen.findByRole("button", { name: "XYZ12A · Bajaj Boxer CT 100" }));
    await userEvent.type(screen.getByLabelText("Kilometraje de llegada"), "15400");
    await userEvent.type(screen.getByLabelText("Qué pide el cliente"), "Aceite");
    await userEvent.click(screen.getByRole("button", { name: "Abrir orden" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("La moto ya tiene una orden de trabajo abierta.");
  });

  it("la ficha muestra la orden, asigna mecánico y deja la historia", async () => {
    const fetch = await openCard(detail(), {
      [`POST ${URL}5/assign/`]: (b) => json(detail({ mechanic: b?.mechanic === 4 ? pablo : null })),
    });
    const aside = card();
    expect(aside).toHaveTextContent("Cliente: Jorge Ramírez · 3001234567 · llegó con 15.400 km");
    expect(aside).toHaveTextContent("Pide: Cambio de aceite y revisar frenos");
    expect(aside).toHaveTextContent("Estado al llegar: Rayón en el tanque, deja el casco");
    expect(aside).toHaveTextContent("Diagnóstico: todavía sin diagnóstico");
    expect(aside).toHaveTextContent("Todavía sin repuestos ni mano de obra.");
    expect(within(aside).getByRole("list", { name: "Historia de la orden" })).toHaveTextContent("Recibida (diana)");
    const select = await within(aside).findByLabelText("Mecánico asignado");
    await within(aside).findByRole("option", { name: "Pablo" });
    await userEvent.selectOptions(select, "Pablo");
    expect(await within(aside).findByRole("status")).toHaveTextContent("Asignada a Pablo.");
    await userEvent.selectOptions(select, "Sin asignar");
    expect(await within(aside).findByRole("status")).toHaveTextContent("Quedó sin mecánico.");
    expect(bodies(fetch, `POST ${URL}5/assign/`)).toEqual([{ mechanic: 4 }, { mechanic: null }]);
    expect(within(aside).queryByRole("button", { name: /Mandar a la caja/ })).not.toBeInTheDocument();
    expect(within(aside).queryByRole("button", { name: "Entregar moto" })).not.toBeInTheDocument();
  });

  it("presupuesto: agrega, pone precio a la mano de obra y quita", async () => {
    const order = detail({ lines: [line(), labor()], pending_total: "32000.00" });
    const fetch = await openCard(order, {
      [`POST ${URL}5/lines/`]: () => json(order, 201),
      [`PATCH ${URL}5/lines/12/`]: () => json(detail({ lines: [line(), labor({ unit_price: "25000.00", total: "25000.00" })], pending_total: "57000.00" })),
      [`DELETE ${URL}5/lines/11/`]: () => json(detail({ lines: [labor()] })),
    });
    const lines = within(card()).getByRole("table", { name: "Líneas del presupuesto" });
    expect(within(lines).getByRole("row", { name: /Aceite 20W50/ })).toHaveTextContent("Aceite 20W50 ACE-20W501$ 32.000$ 32.000Por aprobarQuitar");
    expect(lines).toHaveTextContent("Por aprobar$ 32.000");
    // la mano de obra lleva el precio que pone recepción
    const approve = within(card()).getByRole("button", { name: "Registrar aprobación" });
    expect(approve).toBeDisabled();
    expect(card()).toHaveTextContent("Ponle precio a Mano de obra antes de aprobar.");
    await userEvent.type(within(lines).getByLabelText("Precio de Mano de obra"), "25000");
    await userEvent.click(within(lines).getByRole("button", { name: "Guardar" }));
    expect(bodies(fetch, `PATCH ${URL}5/lines/12/`)).toEqual([{ unit_price: "25000" }]);
    expect(await within(card()).findByRole("status")).toHaveTextContent("Precio de Mano de obra guardado.");
    expect(within(card()).getByRole("button", { name: "Registrar aprobación" })).toBeEnabled();
    // repuesto al precio del catálogo; mano de obra con su precio
    await userEvent.type(within(card()).getByLabelText("Buscar producto"), "Mano");
    await userEvent.click(await within(card()).findByRole("button", { name: /Mano de obra.*servicio/ }));
    await userEvent.type(within(card()).getByLabelText("Precio de este trabajo"), "15000");
    await userEvent.click(within(card()).getByRole("button", { name: "Agregar" }));
    await userEvent.type(within(card()).getByLabelText("Buscar producto"), "Aceite");
    await userEvent.click(await within(card()).findByRole("button", { name: /Aceite 20W50/ }));
    expect(card()).toHaveTextContent("ACE-20W50 · $ 32.000 c/u (precio del catálogo)");
    expect(within(card()).queryByLabelText("Precio de este trabajo")).not.toBeInTheDocument();
    await userEvent.clear(within(card()).getByLabelText("Cantidad"));
    await userEvent.type(within(card()).getByLabelText("Cantidad"), "0");
    expect(within(card()).getByRole("button", { name: "Agregar" })).toBeDisabled();
    await userEvent.clear(within(card()).getByLabelText("Cantidad"));
    await userEvent.type(within(card()).getByLabelText("Cantidad"), "2");
    await userEvent.click(within(card()).getByRole("button", { name: "Agregar" }));
    expect(bodies(fetch, `POST ${URL}5/lines/`)).toEqual([
      { product: "22", quantity: "1", unit_price: "15000" }, { product: "21", quantity: "2" },
    ]);
    expect(await within(card()).findByRole("status")).toHaveTextContent("Aceite 20W50 agregado: queda por aprobar.");
    await userEvent.click(within(within(card()).getByRole("row", { name: /Aceite 20W50/ })).getByRole("button", { name: "Quitar" }));
    expect(bodies(fetch, `DELETE ${URL}5/lines/11/`)).toEqual([undefined]);
    expect(await within(card()).findByRole("status")).toHaveTextContent("Aceite 20W50 quitado.");
  });

  it("registra la aprobación del cliente", async () => {
    const order = detail({ status: "AWAITING_APPROVAL", lines: [line(), labor({ unit_price: "25000.00", total: "25000.00" })], pending_total: "57000.00" });
    const approved = detail({
      status: "IN_REPAIR", lines: [line({ approved: true, taken: true }), labor({ approved: true, unit_price: "25000.00", total: "25000.00" })],
      charged_total: "57000.00", approvals: [{ approved_by: "Jorge", channel: "PHONE", total: "57000.00", recorded_by: "diana", recorded_at: "2026-10-28T17:00:00Z" }],
    });
    const fetch = await openCard(order, { [`POST ${URL}5/approve/`]: () => json(approved) });
    const form = within(card()).getByRole("generic", { name: "Aprobación del cliente" });
    expect(form).toHaveTextContent("Aprobación del cliente ($ 57.000)");
    const who = within(form).getByLabelText("Quién aprobó");
    expect(who).toHaveValue("Jorge Ramírez");
    await userEvent.clear(who);
    expect(within(form).getByRole("button", { name: "Registrar aprobación" })).toBeDisabled();
    await userEvent.type(who, "Jorge");
    await userEvent.selectOptions(within(form).getByLabelText("Cómo"), "Por llamada");
    await userEvent.click(within(form).getByRole("button", { name: "Registrar aprobación" }));
    expect(bodies(fetch, `POST ${URL}5/approve/`)).toEqual([{ approved_by: "Jorge", channel: "PHONE" }]);
    expect(await within(card()).findByRole("status")).toHaveTextContent("Aprobado por Jorge: pasa a reparación.");
    expect(within(card()).getByRole("list", { name: "Aprobaciones" })).toHaveTextContent("aprobó Jorge (por llamada) por $ 57.000 · registró diana");
    expect(within(card()).queryByRole("generic", { name: "Aprobación del cliente" })).not.toBeInTheDocument();
    const oil = within(card()).getByRole("row", { name: /Aceite 20W50/ });
    expect(oil).toHaveTextContent("En la moto");
    expect(within(oil).queryByRole("button", { name: "Quitar" })).not.toBeInTheDocument(); // ya salió: se regresa, no se quita
    expect(within(card()).getByRole("row", { name: /Mano de obra/ })).toHaveTextContent("Aprobada");
    expect(within(card()).queryByLabelText("Precio de Mano de obra")).not.toBeInTheDocument(); // aprobado: el precio no cambia
  });

  it("lista: la manda a la caja y no se entrega hasta que la cobren", async () => {
    const ready = detail({ status: "READY", lines: [line({ approved: true, taken: true })], charged_total: "32000.00" });
    const fetch = await openCard(ready, {
      [`POST ${URL}5/send-to-till/`]: () => json({ ...ready, till_order: { id: 9, code: "4821", total: "32000.00" } }),
    });
    expect(card()).toHaveTextContent("La moto se entrega cuando la caja cobre el pedido.");
    expect(within(card()).queryByLabelText("Agregar al presupuesto")).not.toBeInTheDocument();
    expect(within(card()).queryByRole("button", { name: "Quitar" })).not.toBeInTheDocument();
    await userEvent.click(within(card()).getByRole("button", { name: /^Mandar a la caja \(\$\s32\.000\)$/ }));
    expect(bodies(fetch, `POST ${URL}5/send-to-till/`)).toEqual([{}]);
    expect(await within(card()).findByRole("status")).toHaveTextContent("Mandada a la caja: cóbrala con el código del pedido.");
    expect(card()).toHaveTextContent("En la caja: pedido 4821 por $ 32.000.");
    expect(within(card()).queryByRole("button", { name: /Mandar a la caja/ })).not.toBeInTheDocument();
    expect(within(card()).queryByRole("button", { name: "Entregar moto" })).not.toBeInTheDocument();
  });

  it("cobrada: la entrega con el kilometraje de salida y ya no se cancela", async () => {
    const paid = detail({ status: "READY", sale: { id: 2, number: "POS-0000002", total: "32000.00" }, charged_total: "32000.00" });
    const fetch = await openCard(paid, {
      [`POST ${URL}5/deliver/`]: () => json({ ...paid, status: "DELIVERED", mileage_out: 15420 }),
    });
    expect(card()).toHaveTextContent("Cobrada en la venta POS-0000002 por $ 32.000.");
    expect(within(card()).queryByRole("button", { name: "Cancelar orden" })).not.toBeInTheDocument();
    const form = within(card()).getByRole("generic", { name: "Entregar moto" });
    const km = within(form).getByLabelText("Kilometraje de salida (si cambió)");
    await userEvent.type(km, "15000");
    expect(within(form).getByRole("button", { name: "Entregar moto" })).toBeDisabled();
    await userEvent.type(within(form).getByLabelText("Por qué baja el kilometraje"), "Cambio de tablero");
    expect(within(form).getByRole("button", { name: "Entregar moto" })).toBeEnabled();
    await userEvent.clear(km);
    await userEvent.type(km, "15420");
    expect(within(form).queryByLabelText("Por qué baja el kilometraje")).not.toBeInTheDocument();
    await userEvent.click(within(form).getByRole("button", { name: "Entregar moto" }));
    expect(await within(card()).findByRole("status")).toHaveTextContent("Moto entregada.");
    expect(card()).toHaveTextContent("salió con 15.420 km");
    expect(within(card()).getByText("Entregada", { selector: ".badge" })).toBeInTheDocument();
    expect(within(card()).queryByRole("button", { name: "Entregar moto" })).not.toBeInTheDocument();
    expect(within(card()).queryByLabelText("Mecánico asignado")).not.toBeInTheDocument();
    expect(bodies(fetch, `POST ${URL}5/deliver/`)).toEqual([{ mileage: 15420, mileage_note: "Cambio de tablero" }]);
  });

  it("entregar sin cambiar el kilometraje no lo manda", async () => {
    const paid = detail({ status: "READY", sale: { id: 2, number: "POS-0000002", total: "32000.00" } });
    const fetch = await openCard(paid, { [`POST ${URL}5/deliver/`]: () => json({ ...paid, status: "DELIVERED", mileage_out: 15400 }) });
    await userEvent.click(within(card()).getByRole("button", { name: "Entregar moto" }));
    expect(bodies(fetch, `POST ${URL}5/deliver/`)).toEqual([{ mileage: null, mileage_note: "" }]);
  });

  it("cancela con el motivo y muestra el error del servidor", async () => {
    const fetch = await openCard(detail({ status: "IN_REPAIR" }), {
      [`POST ${URL}5/cancel/`]: (b) => b?.reason === "No volvió"
        ? json(detail({ status: "CANCELLED", events: [{ status: "CANCELLED", note: "No volvió", user: "diana", at: "2026-10-29T15:00:00Z" }] }))
        : json({ reason: ["Escribe por qué se cancela."] }, 400),
    });
    await userEvent.click(within(card()).getByRole("button", { name: "Cancelar orden" }));
    const form = within(card()).getByRole("generic", { name: "Cancelar orden" });
    expect(within(form).getByRole("button", { name: "Cancelar la orden" })).toBeDisabled();
    await userEvent.type(within(form).getByLabelText("Por qué se cancela"), "Otra");
    await userEvent.click(within(form).getByRole("button", { name: "Cancelar la orden" }));
    expect(await within(card()).findByRole("alert")).toHaveTextContent("reason: Escribe por qué se cancela.");
    await userEvent.clear(within(form).getByLabelText("Por qué se cancela"));
    await userEvent.type(within(form).getByLabelText("Por qué se cancela"), " No volvió ");
    await userEvent.click(within(form).getByRole("button", { name: "Cancelar la orden" }));
    expect(await within(card()).findByRole("status")).toHaveTextContent("Orden cancelada: los repuestos que salieron volvieron a la bodega.");
    expect(within(card()).getByRole("list", { name: "Historia de la orden" })).toHaveTextContent("Cancelada (diana) · No volvió");
    expect(within(card()).queryByRole("button", { name: "Cancelar orden" })).not.toBeInTheDocument();
    expect(bodies(fetch, `POST ${URL}5/cancel/`).at(-1)).toEqual({ reason: "No volvió" });
  });

  it("imprime el presupuesto con lo aprobado y lo por aprobar aparte", async () => {
    const order = detail({
      status: "IN_REPAIR", diagnosis: "Aceite vencido", charged_total: "57000.00", pending_total: "18000.00",
      lines: [line({ approved: true, taken: true, quantity: "1.000" }), labor({ approved: true, unit_price: "25000.00", total: "25000.00" }),
        line({ id: 13, sku: "PAS-DEL", name: "Pastillas delanteras", unit_price: "18000.00", total: "18000.00" }),
        line({ id: 14, sku: "BUJ", name: "Bujía", approved: true, taken: true, returned: true })],
    });
    await openCard(order, { "GET /api/invoicing/business/": () => json(business) });
    const print = vi.fn();
    vi.stubGlobal("print", print);
    await userEvent.click(within(card()).getByRole("button", { name: "Imprimir presupuesto" }));
    const dialog = screen.getByRole("dialog", { name: "Imprimir presupuesto" });
    const sheet = within(dialog).getByRole("article", { name: "Hoja de la orden de trabajo" });
    expect(await within(sheet).findByText("Moto Repuestos y Lavadero Arias")).toBeInTheDocument();
    expect(sheet).toHaveTextContent("NIT 900123456-7");
    expect(sheet).toHaveTextContent("Orden de trabajoOT-000005");
    expect(sheet).toHaveTextContent("En reparación");
    expect(sheet).toHaveTextContent("Jorge Ramírez");
    expect(sheet).toHaveTextContent("XYZ12A · Bajaj Boxer CT 100Llegó con 15.400 km");
    expect(sheet).toHaveTextContent("Diagnóstico: Aceite vencido");
    const approved = within(sheet).getByRole("table", { name: "Aprobado" });
    expect(approved).toHaveTextContent("Aceite 20W50");
    expect(approved).toHaveTextContent("Mano de obra (mano de obra)");
    expect(approved).not.toHaveTextContent("Bujía"); // regresada: no se cobra
    expect(approved).toHaveTextContent("Total aprobado$ 57.000");
    const pending = within(sheet).getByRole("table", { name: "Por aprobar" });
    expect(pending).toHaveTextContent("Pastillas delanteras (PAS-DEL)$ 18.000$ 18.000");
    expect(pending).toHaveTextContent("Total por aprobar$ 18.000");
    expect(sheet).not.toHaveTextContent("CANCELADA");
    await userEvent.click(within(dialog).getByRole("button", { name: "Imprimir" }));
    expect(print).toHaveBeenCalledTimes(1);
    await userEvent.click(within(dialog).getByRole("button", { name: "Cerrar" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("la hoja de una orden cancelada lo dice, y sin datos del negocio igual sale", async () => {
    await openCard(detail({ status: "CANCELLED" }), { "GET /api/invoicing/business/": () => json(null) });
    await userEvent.click(within(card()).getByRole("button", { name: "Imprimir presupuesto" }));
    const sheet = screen.getByRole("article", { name: "Hoja de la orden de trabajo" });
    expect(sheet).toHaveTextContent("CANCELADA: esta orden ya no es válida.");
    expect(sheet).toHaveTextContent("Todavía sin repuestos ni mano de obra.");
  });
});
