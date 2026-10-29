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
  return screen.getAllByRole("button").map((b) => b.textContent).filter((t) => t && ["Caja", "Órdenes", "Mis órdenes", "Motos", "Pedidos", "Entradas", "Existencias", "Ventas", "Revisión"].includes(t));
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
  it("recepción ve Órdenes y Motos, y abre en Órdenes, si la instalación tiene el taller (spec 011)", async () => {
    expect(await tabs(["workshop.receive", "sales.create"], { workshop_enabled: true })).toEqual(["Órdenes", "Motos", "Pedidos"]);
    expect(screen.getByRole("heading", { name: "Órdenes de trabajo" })).toBeInTheDocument(); // es la pantalla que abre
  });

  it("sin el módulo (la ferretería) nadie ve Órdenes ni Motos, aunque tenga el permiso", async () => {
    expect(await tabs(["workshop.receive", "sales.create"], { workshop_enabled: false })).toEqual(["Pedidos"]);
  });

  it("una sesión guardada de antes, sin el dato del módulo, lo toma como apagado", async () => {
    expect(await tabs(["workshop.receive", "sales.create"])).toEqual(["Pedidos"]);
  });

  it("el mecánico solo ve Mis órdenes y abre en ella (spec 011)", async () => {
    expect(await tabs(["workshop.repair"], { workshop_enabled: true })).toEqual(["Mis órdenes"]);
    expect(screen.getByRole("heading", { name: "Mis órdenes" })).toBeInTheDocument();
  });

  it("sin el módulo el mecánico no ve nada del taller", async () => {
    expect(await tabs(["workshop.repair"], { workshop_enabled: false })).toEqual([]);
  });

  it("con el módulo, sin el permiso no se ve", async () => {
    expect(await tabs(["cash.operate", "sales.create"], { workshop_enabled: true })).toEqual(["Caja", "Pedidos"]);
  });
});
