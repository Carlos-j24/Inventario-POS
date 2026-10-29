import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "../App";
import { AuthProvider } from "../auth";
import { SyncProvider } from "../sync";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("pantalla de ingreso", () => {
  it("lleva el logo del negocio arriba del formulario", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) => {
      if (url === "/api/auth/csrf/") return Promise.resolve(new Response(null, { status: 204 }));
      if (url === "/api/auth/me/") return Promise.resolve(new Response(JSON.stringify({ detail: "Sin sesión." }), { status: 403 }));
      return Promise.resolve(new Response("[]", { status: 200 }));
    }));
    vi.spyOn(console, "error").mockImplementation(() => {}); // jsdom no trae IndexedDB
    render(<AuthProvider><SyncProvider><App /></SyncProvider></AuthProvider>);
    const heading = await screen.findByRole("heading", { name: "Inventario POS" });
    const logo = screen.getByRole("img", { name: "Logo del negocio" });
    expect(logo).toHaveAttribute("src", "/brand/logo.png");
    expect(logo.compareDocumentPosition(heading) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});
