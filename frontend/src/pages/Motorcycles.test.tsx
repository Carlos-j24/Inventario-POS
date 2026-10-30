import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Customer, Motorcycle, MotorcycleDetail, Owner, Reminder } from "../api";
import Motorcycles from "./Motorcycles";

const URL = "/api/workshop/motorcycles/";
const jorge: Owner = { id: 7, name: "Don Jorge", id_type: "13", id_number: "79123456", check_digit: "", phone: "3001234567" };
const ana: Owner = { id: 8, name: "Ana Pérez", id_type: "13", id_number: "52111222", check_digit: "", phone: "3109998877" };

const moto = (over: Partial<Motorcycle> = {}): Motorcycle => ({
  id: 1, plate: "XYZ12A", vin: "", brand: "Bajaj", model: "Boxer CT 100", year: 2019, displacement_cc: 100, color: "Negro",
  notes: "", is_active: true, mileage: 15200, mileage_at: "2026-10-20T15:00:00Z", owner: jorge,
  created_at: "2026-10-20T15:00:00Z", updated_at: "2026-10-20T15:00:00Z", ...over,
});
const detail = (over: Partial<MotorcycleDetail> = {}): MotorcycleDetail => ({
  ...moto(),
  ownerships: [
    { customer: jorge, started_at: "2026-01-05T15:00:00Z", ended_at: null },
    { customer: ana, started_at: "2024-03-10T15:00:00Z", ended_at: "2026-01-05T15:00:00Z" },
  ],
  mileage_readings: [{ mileage: 15200, previous: 9000, note: "", recorded_at: "2026-10-20T15:00:00Z", recorded_by: "recepcion" }],
  work_orders: [], history: [], reminders: [],
  ...over,
});
const customer = (o: Owner): Customer => ({
  ...o, id_type_label: "Cédula", person_type: "2", email: "", address: "", city: "", tax_responsibilities: [], is_final_consumer: false,
});

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
  fetch.mock.calls.filter(([u, i]) => `${i?.method ?? "GET"} ${u}` === key).map(([, i]) => JSON.parse(String(i?.body)));
const list = { [`GET ${URL}?`]: () => json([moto()]) };

afterEach(() => vi.unstubAllGlobals());

async function openCard(routes: Record<string, Handler> = {}) {
  const fetch = mockApi({ ...list, [`GET ${URL}1/`]: () => json(detail()), ...routes });
  render(<Motorcycles />);
  await userEvent.click(await screen.findByRole("button", { name: "XYZ12A" }));
  await screen.findByRole("heading", { name: "XYZ12A · Bajaj Boxer CT 100" });
  return fetch;
}

async function pickCustomer(query: string, name: RegExp) {
  await userEvent.click(screen.getByRole("button", { name: "Identificar cliente" }));
  await userEvent.type(screen.getByLabelText("Buscar cliente"), query);
  await userEvent.click(await screen.findByRole("button", { name: name }));
}

describe("pantalla Motos", () => {
  it("lista las recientes y busca por lo que se escriba", async () => {
    const fetch = mockApi({
      ...list,
      [`GET ${URL}?q=300+123`]: () => json([]),
      [`GET ${URL}?q=300+123&inactive=1`]: () => json([moto({ id: 2, plate: "", vin: "9FLPCJ", is_active: false })]),
    });
    render(<Motorcycles />);
    const row = await screen.findByRole("row", { name: /XYZ12A/ });
    expect(row).toHaveTextContent("Bajaj Boxer CT 100");
    expect(row).toHaveTextContent("Don Jorge 3001234567");
    expect(row).toHaveTextContent("15.200");
    await userEvent.type(screen.getByLabelText("Buscar moto"), "300 123");
    expect(await screen.findByText("Ninguna moto coincide.")).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText(/Mostrar inactivas/));
    expect(await screen.findByRole("button", { name: "Sin placa" })).toBeInTheDocument();
    // la búsqueda espera a que se deje de escribir: no una consulta por letra
    expect(fetch.mock.calls.filter(([u]) => String(u).startsWith(`${URL}?q=`)).length).toBeLessThanOrEqual(3);
  });

  it("sin motos todavía lo dice", async () => {
    mockApi({ [`GET ${URL}?`]: () => json([]) });
    render(<Motorcycles />);
    expect(await screen.findByText("Todavía no hay motos registradas.")).toBeInTheDocument();
  });

  it("la ficha muestra el dueño, los anteriores y las lecturas", async () => {
    await openCard();
    expect(screen.getByText(/Dueño:/)).toHaveTextContent("Dueño: Don Jorge · 3001234567 · 79123456");
    expect(within(screen.getByLabelText("Dueños anteriores")).getByRole("listitem")).toHaveTextContent(/Ana Pérez · del .*2024 al .*2026/);
    expect(within(screen.getByLabelText("Lecturas de kilometraje")).getByRole("listitem")).toHaveTextContent("15.200 km (recepcion)");
  });
});

describe("registrar una moto", () => {
  it("con un cliente que ya existe, en un solo paso", async () => {
    const fetch = mockApi({
      ...list,
      "GET /api/customers/?q=300": () => json([customer(jorge)]),
      [`POST ${URL}`]: () => json(moto({ id: 3 }), 201),
      [`GET ${URL}3/`]: () => json(detail({ id: 3 })),
    });
    render(<Motorcycles />);
    await userEvent.click(await screen.findByRole("button", { name: "Nueva moto" }));
    const save = screen.getByRole("button", { name: "Registrar moto" });
    expect(save).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Placa"), "xyz-12a");
    await userEvent.type(screen.getByLabelText("Marca"), "Bajaj");
    await userEvent.type(screen.getByLabelText("Kilometraje"), "15200");
    expect(screen.getByText("Elige o registra al dueño.")).toBeInTheDocument();
    expect(save).toBeDisabled(); // los datos están bien, pero falta el dueño
    await pickCustomer("300", /Don Jorge/);
    await userEvent.click(save);
    expect(bodies(fetch, `POST ${URL}`)).toEqual([{
      plate: "XYZ12A", vin: "", brand: "Bajaj", model: "", year: null, displacement_cc: null, color: "", notes: "", owner: 7, mileage: 15200,
    }]);
    expect(await screen.findByRole("heading", { name: "XYZ12A · Bajaj Boxer CT 100" })).toBeInTheDocument();
  });

  it("sin kilometraje va en cero; uno que no es número no se envía", async () => {
    const fetch = mockApi({
      ...list,
      "GET /api/customers/?q=300": () => json([customer(jorge)]),
      [`POST ${URL}`]: () => json(moto({ id: 3 }), 201),
      [`GET ${URL}3/`]: () => json(detail({ id: 3 })),
    });
    render(<Motorcycles />);
    await userEvent.click(await screen.findByRole("button", { name: "Nueva moto" }));
    await pickCustomer("300", /Don Jorge/);
    expect(screen.getByText(/placa o, si no tiene, el número de chasis/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Chasis (si no tiene placa)"), "9flpcj200x");
    await userEvent.type(screen.getByLabelText("Marca"), "Honda");
    await userEvent.type(screen.getByLabelText("Kilometraje"), "15.2");
    expect(screen.getByText("El kilometraje va en números.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Registrar moto" })).toBeDisabled();
    await userEvent.clear(screen.getByLabelText("Kilometraje"));
    await userEvent.click(screen.getByRole("button", { name: "Registrar moto" }));
    expect(bodies(fetch, `POST ${URL}`)[0]).toMatchObject({ plate: "", vin: "9FLPCJ200X", mileage: 0 });
  });

  it("un cliente sin teléfono tiene que dar uno antes de ser el dueño", async () => {
    const noPhone = { ...jorge, phone: "" };
    const fetch = mockApi({
      ...list,
      "GET /api/customers/?q=791": () => json([customer(noPhone)]),
      "PATCH /api/customers/7/": () => json(customer(jorge)),
    });
    render(<Motorcycles />);
    await userEvent.click(await screen.findByRole("button", { name: "Nueva moto" }));
    await pickCustomer("791", /Don Jorge/);
    expect(screen.getByText(/no tiene teléfono/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Guardar teléfono" })).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Teléfono"), " 3001234567 ");
    await userEvent.click(screen.getByRole("button", { name: "Guardar teléfono" }));
    expect(bodies(fetch, "PATCH /api/customers/7/")).toEqual([{ phone: "3001234567" }]);
    expect(await screen.findByText(/Cliente:/)).toHaveTextContent("Cliente: Don Jorge");
    expect(screen.queryByText("Elige o registra al dueño.")).not.toBeInTheDocument();
  });

  it("un cliente nuevo desde el taller necesita teléfono", async () => {
    const fetch = mockApi({ ...list, "POST /api/customers/": () => json(customer(ana), 201) });
    render(<Motorcycles />);
    await userEvent.click(await screen.findByRole("button", { name: "Nueva moto" }));
    await userEvent.click(screen.getByRole("button", { name: "Identificar cliente" }));
    await userEvent.click(screen.getByRole("button", { name: "Nuevo cliente" }));
    await userEvent.type(screen.getByLabelText("Número de documento"), "52111222");
    await userEvent.type(screen.getByLabelText("Nombre o razón social"), "Ana Pérez");
    const save = screen.getByRole("button", { name: "Guardar cliente" });
    expect(save).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Teléfono"), "3109998877");
    await userEvent.click(save);
    expect(bodies(fetch, "POST /api/customers/")[0]).toMatchObject({ id_number: "52111222", name: "Ana Pérez", phone: "3109998877" });
    expect(await screen.findByText("Ana Pérez")).toBeInTheDocument();
  });

  it("muestra lo que rechaza el servidor", async () => {
    mockApi({
      ...list,
      "GET /api/customers/?q=300": () => json([customer(jorge)]),
      [`POST ${URL}`]: () => json({ plate: ["Ya existe una moto con esa placa."] }, 400),
    });
    render(<Motorcycles />);
    await userEvent.click(await screen.findByRole("button", { name: "Nueva moto" }));
    await pickCustomer("300", /Don Jorge/);
    await userEvent.type(screen.getByLabelText("Placa"), "XYZ12A");
    await userEvent.type(screen.getByLabelText("Marca"), "Bajaj");
    await userEvent.click(screen.getByRole("button", { name: "Registrar moto" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Ya existe una moto con esa placa.");
  });
});

describe("la ficha", () => {
  it("bajar el kilometraje pide una nota", async () => {
    const fetch = await openCard({ [`POST ${URL}1/mileage/`]: () => json(detail({ mileage: 120 })) });
    const save = screen.getByRole("button", { name: "Guardar kilometraje" });
    expect(save).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Kilometraje nuevo"), "120");
    expect(save).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Nota del kilometraje"), " Cambio de tablero ");
    await userEvent.click(save);
    expect(bodies(fetch, `POST ${URL}1/mileage/`)).toEqual([{ mileage: 120, note: "Cambio de tablero" }]);
    expect(await screen.findByRole("status")).toHaveTextContent("Kilometraje guardado.");
    expect(screen.getByLabelText("Kilometraje nuevo")).toHaveValue(""); // listo para la próxima lectura
  });

  it("subir el kilometraje no pide nota", async () => {
    const fetch = await openCard({ [`POST ${URL}1/mileage/`]: () => json(detail({ mileage: 16000 })) });
    await userEvent.type(screen.getByLabelText("Kilometraje nuevo"), "16000");
    expect(screen.queryByLabelText("Nota del kilometraje")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Guardar kilometraje" }));
    expect(bodies(fetch, `POST ${URL}1/mileage/`)).toEqual([{ mileage: 16000, note: "" }]);
  });

  it("pasa la moto a otro dueño, pero no al mismo", async () => {
    const fetch = await openCard({
      "GET /api/customers/?q=Ana": () => json([customer(ana)]),
      "GET /api/customers/?q=Jor": () => json([customer(jorge)]),
      [`POST ${URL}1/owner/`]: () => json(detail({ owner: ana })),
    });
    await pickCustomer("Jor", /Don Jorge/);
    expect(screen.getByRole("button", { name: "Ya es el dueño" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Cambiar" }));
    await userEvent.type(screen.getByLabelText("Buscar cliente"), "Ana");
    await userEvent.click(await screen.findByRole("button", { name: /Ana Pérez/ }));
    await userEvent.click(screen.getByRole("button", { name: "Pasar la moto a Ana Pérez" }));
    expect(bodies(fetch, `POST ${URL}1/owner/`)).toEqual([{ owner: 8 }]);
    expect(await screen.findByRole("status")).toHaveTextContent("Ahora es de Ana Pérez.");
    expect(screen.getByText(/Dueño:/)).toHaveTextContent("Ana Pérez");
  });

  it("el aviso no repite el punto de un nombre como \"… S.A.S.\"", async () => {
    const pinos = { ...ana, id: 9, name: "Constructora Los Pinos S.A.S." };
    await openCard({
      "GET /api/customers/?q=pin": () => json([customer(pinos)]),
      [`POST ${URL}1/owner/`]: () => json(detail({ owner: pinos })),
    });
    await pickCustomer("pin", /Constructora/);
    await userEvent.click(screen.getByRole("button", { name: /Pasar la moto/ }));
    expect(await screen.findByRole("status")).toHaveTextContent(/^Ahora es de Constructora Los Pinos S\.A\.S\.$/);
  });

  it("corrige los datos y solo guarda si cambió algo", async () => {
    const fetch = await openCard({ [`PATCH ${URL}1/`]: () => json(detail({ color: "Rojo", updated_at: "2026-10-27T15:00:00Z" })) });
    const save = screen.getByRole("button", { name: "Guardar datos" });
    expect(save).toBeDisabled();
    await userEvent.clear(screen.getByLabelText("Color"));
    await userEvent.type(screen.getByLabelText("Color"), "Rojo");
    await userEvent.click(save);
    expect(bodies(fetch, `PATCH ${URL}1/`)).toEqual([{
      plate: "XYZ12A", vin: "", brand: "Bajaj", model: "Boxer CT 100", year: 2019, displacement_cc: 100, color: "Rojo", notes: "",
    }]);
    expect(await screen.findByRole("status")).toHaveTextContent("Datos guardados.");
    expect(screen.getByRole("button", { name: "Guardar datos" })).toBeDisabled();
  });

  it("no deja guardar datos con un error que se ve antes de enviar", async () => {
    await openCard();
    await userEvent.clear(screen.getByLabelText("Marca"));
    expect(screen.getByText("Escribe la marca.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Guardar datos" })).toBeDisabled();
  });

  it("desactiva y reactiva la moto", async () => {
    const fetch = await openCard({ [`PATCH ${URL}1/`]: (b) => json(detail({ is_active: !!b?.is_active, updated_at: String(Math.random()) })) });
    await userEvent.click(screen.getByRole("button", { name: "Desactivar moto" }));
    expect(await screen.findByText("Inactiva")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Reactivar moto" }));
    expect(bodies(fetch, `PATCH ${URL}1/`)).toEqual([{ is_active: false }, { is_active: true }]);
  });

  it("muestra sus órdenes y la recibe en el taller desde la ficha", async () => {
    const delivered = { id: 4, number: "OT-000004", status: "DELIVERED" as const, mileage_in: 9000, request: "Lavado", received_at: "2026-05-02T15:00:00Z" };
    const opened = { id: 5, number: "OT-000005", status: "RECEIVED" as const, mileage_in: 15400, request: "Cambio de aceite", received_at: "2026-10-28T15:00:00Z" };
    const history = (o: typeof delivered | typeof opened) => ({
      ...o, delivered_at: null, mileage_out: null, diagnosis: "", mechanic: null, lines: [], total: null,
    });
    let received = false;
    const fetch = await openCard({
      [`GET ${URL}1/`]: () => json(detail({
        mileage: received ? 15400 : 15200, work_orders: received ? [opened, delivered] : [delivered],
        history: received ? [history(opened), { ...history(delivered), delivered_at: "2026-05-02T15:00:00Z", mileage_out: 9000, total: "12000.00" }]
          : [{ ...history(delivered), delivered_at: "2026-05-02T15:00:00Z", mileage_out: 9000, total: "12000.00" }],
      })),
      "GET /api/workshop/orders/mechanics/": () => json([{ id: 3, username: "carlos", name: "Carlos" }]),
      "POST /api/workshop/orders/": () => { received = true; return json({ ...opened, lines: [] }, 201); },
    });
    expect(screen.getByRole("list", { name: "Historial de la moto" })).toHaveTextContent("OT-000004 · Entregada el 2 de may de 2026 con 9.000 km");
    await userEvent.click(screen.getByRole("button", { name: "Recibir en el taller" }));
    const form = screen.getByRole("form", { name: "Recibir moto" });
    expect(form).toHaveTextContent("Recibir XYZ12A · Bajaj Boxer CT 100");
    await userEvent.type(within(form).getByLabelText("Kilometraje de llegada"), "15400");
    await userEvent.type(within(form).getByLabelText("Qué pide el cliente"), "Cambio de aceite");
    await userEvent.click(within(form).getByRole("button", { name: "Abrir orden" }));
    expect(bodies(fetch, "POST /api/workshop/orders/")).toEqual([{
      motorcycle: 1, mileage: 15400, mileage_note: "", request: "Cambio de aceite", condition: "", mechanic: null,
    }]);
    expect(await screen.findByRole("status")).toHaveTextContent("Orden OT-000005 abierta: síguela en Órdenes.");
    expect(await screen.findByText("Tiene abierta la orden OT-000005: síguela en Órdenes.")).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Historial de la moto" })).toHaveTextContent("OT-000005 · Recibida · recibida el 28 de oct de 2026 con 15.400 km");
    expect(screen.queryByRole("button", { name: "Recibir en el taller" })).not.toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "Recibir moto" })).not.toBeInTheDocument();
  });

  it("el historial dice qué se le hizo en cada orden entregada, y sus mantenimientos (spec 012)", async () => {
    const reminder = (over: Partial<Reminder>): Reminder => ({
      id: 1, plan: { id: 1, name: "Cambio de aceite" }, status: "PENDING", due_date: "2027-01-28", due_mileage: 18420, due_on: "2027-01-28",
      by_km: false, estimated: false, daily_km: null, note: "", source_order: "OT-000004", done_order: null, notices: [], closed_at: null, ...over,
    });
    await openCard({
      [`GET ${URL}1/`]: () => json(detail({
        history: [{
          id: 4, number: "OT-000004", status: "DELIVERED", received_at: "2026-10-28T15:00:00Z", delivered_at: "2026-10-30T15:00:00Z",
          mileage_in: 15400, mileage_out: 15420, request: "Cambio de aceite y revisar frenos", diagnosis: "Aceite vencido", mechanic: "Jhon",
          lines: [
            { sku: "ACE-20W50", name: "Aceite 20W50", is_service: false, quantity: "1.000", total: "32000.00" },
            { sku: "MO-TALLER", name: "Mano de obra", is_service: true, quantity: "1.000", total: "25000.00" },
          ],
          total: "57000.00",
        }],
        reminders: [
          reminder({}),
          reminder({ id: 2, plan: { id: 2, name: "Revisión de frenos" }, status: "DONE", due_date: "2026-10-01", due_mileage: null,
            due_on: null, done_order: "OT-000004", closed_at: "2026-10-30T15:00:00Z" }),
          reminder({ id: 3, plan: { id: 3, name: "Kit de arrastre" }, status: "DISMISSED", due_date: null, due_mileage: 30000,
            due_on: null, note: "Vendió el kit aparte", closed_at: "2026-10-30T15:00:00Z" }),
        ],
      })),
    });
    const item = within(screen.getByRole("list", { name: "Historial de la moto" })).getAllByRole("listitem")[0];
    expect(item).toHaveTextContent("OT-000004 · Entregada el 30 de oct de 2026 con 15.420 km · Jhon");
    expect(item).toHaveTextContent("Pide: Cambio de aceite y revisar frenos");
    expect(item).toHaveTextContent("Diagnóstico: Aceite vencido");
    const done = screen.getByRole("list", { name: "Lo que se le hizo en OT-000004" });
    expect(done).toHaveTextContent(/1 × Aceite 20W50 ACE-20W50 · \$\s32\.000/);
    expect(done).toHaveTextContent(/1 × Mano de obra mano de obra · \$\s25\.000/);
    expect(item).toHaveTextContent(/Total: \$\s57\.000/);
    const plans = screen.getByRole("list", { name: "Mantenimientos de la moto" });
    expect(plans).toHaveTextContent("Cambio de aceite: el 28 de enero de 2027 o a los 18.420 km · Pendiente · Vence en");
    expect(plans).toHaveTextContent("Revisión de frenos: el 1 de octubre de 2026 · Hecho · con la orden OT-000004");
    expect(plans).not.toHaveTextContent("Hecho · Vence"); // cerrado: no dice cuándo vence
    expect(plans).toHaveTextContent("Kit de arrastre: a los 30.000 km · Descartado · Vendió el kit aparte");
  });

  it("sin órdenes lo dice y cancelar cierra el formulario", async () => {
    await openCard();
    expect(screen.getByText("Todavía no ha entrado al taller.")).toBeInTheDocument();
    expect(screen.getByText("Sin mantenimientos programados: se calculan al entregar una orden.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Recibir en el taller" }));
    await userEvent.click(within(screen.getByRole("form", { name: "Recibir moto" })).getByRole("button", { name: "Cancelar" }));
    expect(screen.queryByRole("form", { name: "Recibir moto" })).not.toBeInTheDocument();
  });

  it("una moto inactiva no se recibe en el taller", async () => {
    mockApi({ ...list, [`GET ${URL}1/`]: () => json(detail({ is_active: false })) });
    render(<Motorcycles />);
    await userEvent.click(await screen.findByRole("button", { name: "XYZ12A" }));
    await screen.findByRole("heading", { name: "XYZ12A · Bajaj Boxer CT 100" });
    expect(screen.queryByRole("button", { name: "Recibir en el taller" })).not.toBeInTheDocument();
  });
});
