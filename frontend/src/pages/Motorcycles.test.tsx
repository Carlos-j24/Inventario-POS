import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Customer, Motorcycle, MotorcycleDetail, Owner } from "../api";
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
});
