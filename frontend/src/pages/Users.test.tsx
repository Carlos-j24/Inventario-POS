import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { AppUser, Role } from "../api";
import { AuthProvider } from "../auth";
import Users from "./Users";

const user = (over: Partial<AppUser>): AppUser => ({
  id: 1, username: "u", first_name: "", last_name: "", email: "", is_active: true, roles: [],
  must_change_password: false, last_login: null, ...over,
});

const people = [
  user({ id: 1, username: "admin", roles: ["Administrador"] }),
  user({ id: 2, username: "laura.caja", first_name: "Laura", roles: ["Caja"] }),
  user({ id: 3, username: "ex.cajero", is_active: false, roles: ["Caja"] }),
  user({ id: 4, username: "pedro.nuevo", must_change_password: true, roles: ["Auxiliar de bodega"] }),
];
const roles: Role[] = [
  { id: 1, name: "Administrador", permissions: [] },
  { id: 2, name: "Caja", permissions: [] },
  { id: 3, name: "Supervisor", permissions: [] },
];

type Handler = (body: Record<string, unknown> | undefined) => Response;

function mockApi(routes: Record<string, Handler>) {
  const fn = vi.fn((url: string, init?: RequestInit) => {
    const key = `${init?.method ?? "GET"} ${url}`;
    const h = routes[key];
    return h ? Promise.resolve(h(init?.body ? JSON.parse(String(init.body)) : undefined)) : Promise.reject(new Error(`no simulada: ${key}`));
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const base = {
  "GET /api/accounts/users/": () => json(people),
  "GET /api/accounts/roles/": () => json(roles),
};
const bodies = (fetch: ReturnType<typeof mockApi>, key: string) =>
  fetch.mock.calls.filter(([u, i]) => `${i?.method ?? "GET"} ${u}` === key).map(([, i]) => JSON.parse(String(i?.body)));

afterEach(() => vi.unstubAllGlobals());

describe("pantalla Usuarios", () => {
  it("lista los activos con sus roles y marca la clave temporal; los inactivos, a pedido", async () => {
    mockApi(base);
    render(<Users />);
    expect(await screen.findByRole("row", { name: /laura\.caja/ })).toHaveTextContent("Caja");
    expect(screen.getByRole("row", { name: /pedro\.nuevo/ })).toHaveTextContent("Clave temporal");
    expect(screen.queryByText("ex.cajero")).not.toBeInTheDocument();
    await userEvent.click(screen.getByLabelText(/Mostrar inactivos/));
    expect(screen.getByRole("row", { name: /ex\.cajero/ })).toHaveTextContent("Inactivo");
  });

  it("crea un usuario con contraseña temporal y roles", async () => {
    const fetch = mockApi({
      ...base,
      "POST /api/accounts/users/": () => json(user({ id: 9, username: "maria", roles: ["Caja"], must_change_password: true }), 201),
    });
    render(<Users />);
    await userEvent.click(await screen.findByRole("button", { name: "Nuevo usuario" }));
    await userEvent.type(screen.getByLabelText("Usuario"), "maria");
    await userEvent.type(screen.getByLabelText("Nombre"), "María");
    await userEvent.type(screen.getByLabelText("Contraseña temporal"), "Temporal-2026!");
    await userEvent.click(screen.getByLabelText("Caja"));
    await userEvent.click(screen.getByRole("button", { name: "Crear usuario" }));
    expect(bodies(fetch, "POST /api/accounts/users/")).toEqual([
      { username: "maria", first_name: "María", last_name: "", password: "Temporal-2026!", roles: ["Caja"] },
    ]);
  });

  it("guarda los roles solo si cambiaron", async () => {
    const fetch = mockApi({ ...base, "PATCH /api/accounts/users/2/": () => json(people[1]) });
    render(<Users />);
    await userEvent.click(await screen.findByRole("button", { name: "laura.caja" }));
    const save = screen.getByRole("button", { name: "Guardar roles" });
    expect(save).toBeDisabled();
    await userEvent.click(screen.getByLabelText("Supervisor"));
    await userEvent.click(save);
    expect(bodies(fetch, "PATCH /api/accounts/users/2/")).toEqual([{ roles: ["Caja", "Supervisor"] }]);
    expect(await screen.findByRole("status")).toHaveTextContent("Roles guardados");
  });

  it("si el servidor rechaza la contraseña, la deja escrita y muestra el motivo", async () => {
    let attempt = 0;
    mockApi({
      ...base,
      "PATCH /api/accounts/users/2/": () =>
        ++attempt === 1 ? json({ non_field_errors: ["Esta contraseña es demasiado corta."] }, 400) : json(people[1]),
    });
    render(<Users />);
    await userEvent.click(await screen.findByRole("button", { name: "laura.caja" }));
    const field = screen.getByLabelText("Contraseña nueva");
    await userEvent.type(field, "123");
    await userEvent.click(screen.getByRole("button", { name: "Poner contraseña" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("demasiado corta");
    expect(field).toHaveValue("123");

    await userEvent.clear(field);
    await userEvent.type(field, "Otra-Temporal-2026!");
    await userEvent.click(screen.getByRole("button", { name: "Poner contraseña" }));
    expect(await screen.findByRole("status")).toHaveTextContent("deberá cambiarla");
    expect(field).toHaveValue("");
  });

  it("muestra el error del servidor al desactivar (p. ej. el último administrador)", async () => {
    mockApi({
      ...base,
      "PATCH /api/accounts/users/2/": () => json(["El sistema debe conservar al menos un usuario activo que administre usuarios."], 400),
    });
    render(<Users />);
    await userEvent.click(await screen.findByRole("button", { name: "laura.caja" }));
    await userEvent.click(screen.getByRole("button", { name: "Desactivar usuario" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("al menos un usuario activo");
  });

  it("no deja desactivarse a uno mismo", async () => {
    const me = { id: 1, username: "admin", first_name: "", last_name: "", roles: ["Administrador"], permissions: ["users.manage"], must_change_password: false };
    mockApi({
      ...base,
      "GET /api/auth/csrf/": () => new Response(null, { status: 204 }),
      "GET /api/auth/me/": () => json(me),
    });
    render(<AuthProvider><Users /></AuthProvider>);
    await userEvent.click(await screen.findByRole("button", { name: "admin" }));
    const panel = screen.getByRole("heading", { name: "admin" }).parentElement!;
    expect(within(panel).getByRole("button", { name: "Desactivar usuario" })).toBeDisabled();
    expect(within(panel).getByText(/no puedes desactivarte a ti mismo/)).toBeInTheDocument();
  });
});
