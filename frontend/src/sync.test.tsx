import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "./auth";
import { SyncProvider, useSync } from "./sync";

const me = { id: 1, username: "laura", first_name: "", last_name: "", roles: ["Caja"], permissions: ["cash.operate"] };

function Status() {
  const { online } = useSync();
  return <p>{online ? "En línea" : "Sin conexión"}</p>;
}

/** fetch falso por URL: la sesión responde y /api/health/ hace lo que diga el test. */
function mockServer(health: () => Promise<Response>) {
  vi.stubGlobal("fetch", vi.fn((url: string) => {
    if (url === "/api/auth/csrf/") return Promise.resolve(new Response(null, { status: 204 }));
    if (url === "/api/auth/me/") return Promise.resolve(new Response(JSON.stringify(me), { status: 200 }));
    if (url === "/api/health/") return health();
    return Promise.reject(new Error(`URL inesperada ${url}`));
  }));
}

function renderStatus() {
  render(
    <AuthProvider>
      <SyncProvider>
        <Status />
      </SyncProvider>
    </AuthProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("indicador de conexión", () => {
  // Fallo encontrado en Chrome: con el servidor apagado y sin ventas pendientes decía "En línea".
  it("dice 'Sin conexión' si el servidor no contesta, aunque el equipo tenga red", async () => {
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(true);
    mockServer(() => Promise.reject(new TypeError("Failed to fetch")));
    renderStatus();
    expect(await screen.findByText("Sin conexión")).toBeInTheDocument();
  });

  it("dice 'Sin conexión' si el servidor contesta pero la base de datos no (503)", async () => {
    mockServer(() => Promise.resolve(new Response(JSON.stringify({ status: "error" }), { status: 503 })));
    renderStatus();
    expect(await screen.findByText("Sin conexión")).toBeInTheDocument();
  });

  it("dice 'En línea' si el servidor contesta", async () => {
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    vi.spyOn(console, "error").mockImplementation(() => {}); // jsdom no trae IndexedDB
    mockServer(() => Promise.resolve(new Response(JSON.stringify({ status: "ok" }), { status: 200 })));
    renderStatus();
    expect(await screen.findByText("En línea")).toBeInTheDocument();
  });
});
