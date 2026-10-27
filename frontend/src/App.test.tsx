import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { AuthProvider } from "./auth";
import { SyncProvider } from "./sync";

/** Servidor falso: la sesión de `permissions` y listas vacías para lo demás. */
function serve(permissions: string[], extra: Record<string, unknown> = {}) {
  const me = { id: 1, username: "u", first_name: "", last_name: "", roles: [], permissions, must_change_password: false, ...extra };
  vi.stubGlobal("fetch", vi.fn((url: string) => {
    if (url === "/api/auth/csrf/") return Promise.resolve(new Response(null, { status: 204 }));
    if (url === "/api/auth/me/") return Promise.resolve(new Response(JSON.stringify(me), { status: 200 }));
    return Promise.resolve(new Response(JSON.stringify(url === "/api/health/" ? { status: "ok" } : []), { status: 200 }));
  }));
  vi.spyOn(console, "error").mockImplementation(() => {}); // jsdom no trae IndexedDB
}

async function tabs(permissions: string[], extra: Record<string, unknown> = {}) {
  serve(permissions, extra);
  render(<AuthProvider><SyncProvider><App /></SyncProvider></AuthProvider>);
  await screen.findByRole("button", { name: "Salir" });
  return screen.getAllByRole("button").map((b) => b.textContent).filter((t) => t && ["Caja", "Motos", "Pedidos", "Entradas", "Existencias", "Ventas", "Revisión"].includes(t));
}

afterEach(() => vi.restoreAllMocks());
afterEach(() => vi.unstubAllGlobals());

describe("navegación por permisos", () => {
  it("el cajero ve Caja y Pedidos, no Ventas", async () => {
    expect(await tabs(["cash.operate", "sales.create"])).toEqual(["Caja", "Pedidos"]);
  });

  it("basta con uno de los permisos de una pantalla: el jefe de bodega ve Ventas por tener reportes", async () => {
    const seen = await tabs(["inventory.view", "inventory.receive", "reports.view"]);
    expect(seen).toContain("Ventas");
    expect(seen).not.toContain("Caja");
  });

  it("el supervisor ve Ventas por poder anular", async () => {
    expect(await tabs(["sales.void"])).toEqual(["Ventas"]);
  });
});

describe("módulo de taller (spec 009)", () => {
  it("recepción ve Motos primero si la instalación tiene el taller", async () => {
    expect(await tabs(["workshop.receive", "sales.create"], { workshop_enabled: true })).toEqual(["Motos", "Pedidos"]);
    expect(screen.getByRole("heading", { name: "Motos" })).toBeInTheDocument(); // es la pantalla que abre
  });

  it("sin el módulo (la ferretería) nadie ve Motos, aunque tenga el permiso", async () => {
    expect(await tabs(["workshop.receive", "sales.create"], { workshop_enabled: false })).toEqual(["Pedidos"]);
  });

  it("una sesión guardada de antes, sin el dato del módulo, lo toma como apagado", async () => {
    expect(await tabs(["workshop.receive", "sales.create"])).toEqual(["Pedidos"]);
  });

  it("con el módulo, sin el permiso no se ve", async () => {
    expect(await tabs(["cash.operate", "sales.create"], { workshop_enabled: true })).toEqual(["Caja", "Pedidos"]);
  });
});
