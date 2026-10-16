import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "../App";
import { AuthProvider } from "../auth";
import { SyncProvider } from "../sync";

const maria = {
  id: 9, username: "maria.caja", first_name: "María", last_name: "", roles: ["Caja"],
  permissions: ["cash.operate", "sales.create"], must_change_password: true,
};

type Handler = (body?: Record<string, string>) => Response;

function serve(routes: Record<string, Handler>) {
  const fn = vi.fn((url: string, init?: RequestInit) => {
    const key = `${init?.method ?? "GET"} ${url}`;
    const h = routes[key];
    if (h) return Promise.resolve(h(init?.body ? JSON.parse(String(init.body)) : undefined));
    // Lo demás (cajas, catálogo, salud…) responde vacío: aquí no importa.
    return Promise.resolve(new Response(JSON.stringify(url === "/api/health/" ? { status: "ok" } : []), { status: 200 }));
  });
  vi.stubGlobal("fetch", fn);
  vi.spyOn(console, "error").mockImplementation(() => {}); // jsdom no trae IndexedDB
  return fn;
}

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const session = (me: object) => ({
  "GET /api/auth/csrf/": () => new Response(null, { status: 204 }),
  "GET /api/auth/me/": () => json(me),
});

function renderApp() {
  render(<AuthProvider><SyncProvider><App /></SyncProvider></AuthProvider>);
}

async function fill(current: string, next: string, repeat = next) {
  await userEvent.type(screen.getByLabelText(/Contraseña temporal|Contraseña actual/), current);
  await userEvent.type(screen.getByLabelText("Nueva contraseña"), next);
  await userEvent.type(screen.getByLabelText("Repite la nueva"), repeat);
}

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe("contraseña temporal (primer ingreso)", () => {
  it("con clave temporal solo se ve la pantalla de cambio; al cambiarla aparece la app", async () => {
    const fetch = serve({
      ...session(maria),
      "POST /api/auth/password/": () => json({ ...maria, must_change_password: false }),
    });
    renderApp();
    expect(await screen.findByRole("heading", { name: "Hola, María" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Caja" })).not.toBeInTheDocument();

    await fill("Temporal-Maria-2026", "Mi-Clave-Propia-2026");
    await userEvent.click(screen.getByRole("button", { name: "Cambiar contraseña" }));

    expect(await screen.findByRole("button", { name: "Caja" })).toBeInTheDocument();
    const call = fetch.mock.calls.find(([u, i]) => u === "/api/auth/password/" && i?.method === "POST")!;
    expect(JSON.parse(String(call[1]!.body))).toEqual({ current_password: "Temporal-Maria-2026", new_password: "Mi-Clave-Propia-2026" });
  });

  it("si la nueva no coincide no deja enviar; si el servidor la rechaza, lo dice", async () => {
    serve({
      ...session(maria),
      "POST /api/auth/password/": () => json({ new_password: ["Esta contraseña es demasiado común."] }, 400),
    });
    renderApp();
    await screen.findByRole("heading", { name: "Hola, María" });
    await fill("Temporal-Maria-2026", "password123", "password124");
    expect(screen.getByText("Las contraseñas nuevas no coinciden.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cambiar contraseña" })).toBeDisabled();

    await userEvent.clear(screen.getByLabelText("Repite la nueva"));
    await userEvent.type(screen.getByLabelText("Repite la nueva"), "password123");
    await userEvent.click(screen.getByRole("button", { name: "Cambiar contraseña" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("demasiado común");
    expect(screen.getByRole("heading", { name: "Hola, María" })).toBeInTheDocument(); // sigue bloqueada
  });
});

describe("cambiar mi contraseña", () => {
  it("desde el nombre en la cabecera, sin cerrar la sesión", async () => {
    serve({
      ...session({ ...maria, must_change_password: false }),
      "POST /api/auth/password/": () => json({ ...maria, must_change_password: false }),
    });
    renderApp();
    await userEvent.click(await screen.findByRole("button", { name: /María · Caja/ }));
    expect(screen.getByRole("heading", { name: "Cambiar mi contraseña" })).toBeInTheDocument();
    await fill("Vieja-Clave-2026", "Nueva-Clave-2026");
    await userEvent.click(screen.getByRole("button", { name: "Cambiar contraseña" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Contraseña cambiada.");
    expect(screen.getByRole("button", { name: "Caja" })).toBeInTheDocument();
  });
});
