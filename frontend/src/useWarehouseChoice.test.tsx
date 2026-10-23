import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Warehouse } from "./api";
import { AuthProvider } from "./auth";
import { useWarehouseChoice } from "./useWarehouseChoice";

const pral: Warehouse = { id: 1, code: "PRAL", name: "Bodega principal", is_default: true };
const loc: Warehouse = { id: 2, code: "LOC", name: "Local", is_default: false };
const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200 });

/** Las bodegas llegan antes que el usuario: así se ve si se propone antes de saber quién es. */
function mockApi(username: string, warehouses: Warehouse[] = [pral, loc]) {
  let release!: () => void;
  const me = new Promise<Response>((resolve) => {
    release = () => resolve(json({ id: 1, username, first_name: "", last_name: "", roles: [], permissions: [], must_change_password: false }));
  });
  vi.stubGlobal("fetch", vi.fn((url: string) => {
    if (url === "/api/auth/csrf/") return Promise.resolve(new Response(null, { status: 204 }));
    if (url === "/api/auth/me/") return me;
    if (url === "/api/inventory/warehouses/") return Promise.resolve(json(warehouses));
    return Promise.reject(new Error(`ruta no simulada: ${url}`));
  }));
  return release;
}

function Picker() {
  const { warehouses, warehouse, choose } = useWarehouseChoice(() => {});
  return (
    <>
      <select aria-label="Bodega" value={warehouse ?? ""} onChange={(e) => choose(Number(e.target.value))}>
        {warehouses.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
      </select>
      <output aria-label="Elegida">{warehouse ?? "ninguna"}</output>
    </>
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("useWarehouseChoice", () => {
  it("la primera vez propone la principal y recuerda lo que el usuario elige", async () => {
    const release = mockApi("pedro");
    const { unmount } = render(<AuthProvider><Picker /></AuthProvider>);
    await screen.findByRole("option", { name: "Local" });
    expect(screen.getByLabelText("Elegida")).toHaveTextContent("ninguna"); // todavía no sabe quién es
    release();
    await vi.waitFor(() => expect(screen.getByLabelText("Elegida")).toHaveTextContent("1"));
    await userEvent.selectOptions(screen.getByLabelText("Bodega"), "2");
    expect(localStorage.getItem("inventario.bodega.pedro")).toBe("2");
    unmount();

    mockApi("pedro")(); // vuelve a la pantalla (u otra de inventario) en el mismo equipo
    render(<AuthProvider><Picker /></AuthProvider>);
    await vi.waitFor(() => expect(screen.getByLabelText("Elegida")).toHaveTextContent("2"));
  });

  it("aunque las bodegas lleguen antes que el usuario, propone la que él recuerda", async () => {
    localStorage.setItem("inventario.bodega.pedro", "2");
    const release = mockApi("pedro");
    render(<AuthProvider><Picker /></AuthProvider>);
    await screen.findByRole("option", { name: "Local" });
    await new Promise((resolve) => setTimeout(resolve, 30)); // las bodegas ya están; el usuario todavía no
    release();
    await vi.waitFor(() => expect(screen.getByLabelText("Elegida")).toHaveTextContent("2"));
  });

  it("si la persona elige antes de que cargue el usuario, se respeta su elección", async () => {
    const release = mockApi("pedro");
    render(<AuthProvider><Picker /></AuthProvider>);
    await screen.findByRole("option", { name: "Local" });
    await userEvent.selectOptions(screen.getByLabelText("Bodega"), "2");
    release();
    await new Promise((resolve) => setTimeout(resolve, 30));
    expect(screen.getByLabelText("Elegida")).toHaveTextContent("2");
  });

  it("a otro usuario en el mismo equipo le propone la principal", async () => {
    localStorage.setItem("inventario.bodega.pedro", "2");
    mockApi("marta")();
    render(<AuthProvider><Picker /></AuthProvider>);
    await vi.waitFor(() => expect(screen.getByLabelText("Elegida")).toHaveTextContent("1"));
  });

  it("si la recordada ya no está activa, propone la principal", async () => {
    localStorage.setItem("inventario.bodega.pedro", "7");
    mockApi("pedro")();
    render(<AuthProvider><Picker /></AuthProvider>);
    await vi.waitFor(() => expect(screen.getByLabelText("Elegida")).toHaveTextContent("1"));
  });
});
