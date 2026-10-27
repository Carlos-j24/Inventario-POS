import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { PermissionInfo, Role } from "../api";
import Roles, { groupPermissions } from "./Roles";

const perms: PermissionInfo[] = [
  { code: "cash.operate", description: "Abrir, cobrar y cerrar caja" },
  { code: "inventory.receive", description: "Registrar entradas a bodega" },
  { code: "inventory.view", description: "Ver existencias y kardex" },
  { code: "sales.create", description: "Crear ventas y cotizaciones" },
];
const roles: Role[] = [{ id: 5, name: "Caja", permissions: ["cash.operate", "sales.create"] }];

type Handler = (body?: Record<string, unknown>) => Response;

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
const base = { "GET /api/accounts/roles/": () => json(roles), "GET /api/accounts/permissions/": () => json(perms) };
const bodyOf = (fetch: ReturnType<typeof mockApi>, key: string) =>
  JSON.parse(String(fetch.mock.calls.find(([u, i]) => `${i?.method ?? "GET"} ${u}` === key)![1]!.body));

afterEach(() => vi.unstubAllGlobals());

it("agrupa los permisos por tema", () => {
  expect(groupPermissions(perms).map((g) => [g.group, g.items.length])).toEqual([["Caja", 1], ["Inventario", 2], ["Ventas", 1]]);
  expect(groupPermissions([{ code: "workshop.receive", description: "Recibir motos" }])[0].group).toBe("Taller");
});

describe("pantalla Roles", () => {
  it("edita los permisos de un rol por defecto, en lenguaje claro", async () => {
    const fetch = mockApi({ ...base, "PATCH /api/accounts/roles/5/": (b) => json({ id: 5, ...b }) });
    render(<Roles />);
    await userEvent.click(await screen.findByRole("button", { name: /^Caja.*2 permiso/ }));
    const save = screen.getByRole("button", { name: "Guardar rol" });
    expect(save).toBeDisabled(); // sin cambios
    await userEvent.click(screen.getByLabelText("Ver existencias y kardex"));
    await userEvent.click(save);
    expect(bodyOf(fetch, "PATCH /api/accounts/roles/5/")).toEqual({
      name: "Caja", permissions: ["cash.operate", "sales.create", "inventory.view"],
    });
    expect(await screen.findByRole("status")).toHaveTextContent("al recargar la app");
  });

  it("crea un rol nuevo", async () => {
    const fetch = mockApi({ ...base, "POST /api/accounts/roles/": (b) => json({ id: 9, ...b }, 201) });
    render(<Roles />);
    await userEvent.click(await screen.findByRole("button", { name: "Nuevo rol" }));
    await userEvent.type(screen.getByLabelText("Nombre"), "Comprador");
    await userEvent.click(screen.getByLabelText("Registrar entradas a bodega"));
    await userEvent.click(screen.getByRole("button", { name: "Crear rol" }));
    expect(bodyOf(fetch, "POST /api/accounts/roles/")).toEqual({ name: "Comprador", permissions: ["inventory.receive"] });
  });

  it("muestra el rechazo del servidor (p. ej. quedarse sin administradores)", async () => {
    mockApi({
      ...base,
      "PATCH /api/accounts/roles/5/": () => json({ non_field_errors: ["El sistema debe conservar al menos un usuario activo que administre usuarios."] }, 400),
    });
    render(<Roles />);
    await userEvent.click(await screen.findByRole("button", { name: /^Caja.*2 permiso/ }));
    await userEvent.click(screen.getByLabelText("Abrir, cobrar y cerrar caja"));
    await userEvent.click(screen.getByRole("button", { name: "Guardar rol" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("al menos un usuario activo");
  });
});
