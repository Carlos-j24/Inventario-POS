import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "../auth";
import { presetPeriod } from "../reports";
import { inventory, margins, products, sales, shifts } from "./reportFixtures";
import Reports from "./Reports";
import { todayIso } from "./Sales";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

function mockApi(routes: Record<string, () => Response>) {
  const fn = vi.fn((url: string) => {
    const route = routes[url] ?? (url.startsWith("/api/reports/") ? routes[url.split("?")[0]] : undefined);
    return route ? Promise.resolve(route()) : Promise.reject(new Error(`ruta no simulada: ${url}`));
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

const urls = (fetch: ReturnType<typeof mockApi>) => fetch.mock.calls.map(([u]) => u);

afterEach(() => vi.unstubAllGlobals());

const registers = () => json([{ id: 2, code: "CAJA2", name: "Caja 2", warehouse: "PRAL", open_shift: null }]);

const base = {
  "/api/cash/registers/": registers,
  "/api/reports/sales/": () => json(sales),
  "/api/reports/products/": () => json(products),
  "/api/reports/shifts/": () => json(shifts),
  "/api/reports/inventory/": () => json(inventory),
  "/api/reports/margins/": () => json(margins),
};

const today = todayIso();

describe("pantalla Reportes", () => {
  it("abre en Ventas de hoy con totales y desgloses", async () => {
    const fetch = mockApi(base);
    render(<Reports />);

    const kpi = (await screen.findByText("Venta neta")).parentElement!;
    expect(kpi).toHaveTextContent(/1\.200\.100/);
    expect(screen.getByText("Ticket promedio").parentElement).toHaveTextContent(/157\.012,5/);
    expect(screen.getByRole("button", { name: "Hoy" })).toHaveAttribute("aria-pressed", "true");
    expect(urls(fetch)).toContain(`/api/reports/sales/?from=${today}&to=${today}`);

    const days = screen.getByRole("table", { name: "Por día" });
    expect(within(days).getByRole("row", { name: /16 (de )?oct/ })).toHaveTextContent(/56\.000.*220\.000/);
    expect(within(days).getByRole("row", { name: /15 (de )?oct/ })).toHaveTextContent("—"); // sin devoluciones
    expect(screen.getByRole("table", { name: "Por vendedor" })).toHaveTextContent("andres.ventas");
    expect(screen.getByRole("table", { name: "Por medio de pago" })).toHaveTextContent(/Efectivo.*960\.100.*56\.000.*904\.100/);
  });

  it("los accesos rápidos, el rango y la caja cambian la consulta", async () => {
    const fetch = mockApi(base);
    render(<Reports />);
    await screen.findByText("Venta neta");

    await userEvent.click(screen.getByRole("button", { name: "Esta semana" }));
    const week = presetPeriod("week", today);
    expect(urls(fetch)).toContain(`/api/reports/sales/?from=${week.from}&to=${today}`);
    expect(screen.getByRole("button", { name: "Esta semana" })).toHaveAttribute("aria-pressed", "true");

    const yesterday = presetPeriod("yesterday", today).from;
    await userEvent.click(screen.getByRole("button", { name: "Ayer" }));
    expect(urls(fetch)).toContain(`/api/reports/sales/?from=${yesterday}&to=${yesterday}`);

    // Una fecha inicial posterior a la final arrastra la final.
    fireEvent.change(screen.getByLabelText("Desde"), { target: { value: today } });
    expect(screen.getByLabelText("Hasta")).toHaveValue(today);
    fireEvent.change(screen.getByLabelText("Hasta"), { target: { value: "2026-01-05" } });
    expect(screen.getByLabelText("Desde")).toHaveValue("2026-01-05");
    expect(screen.getByRole("button", { name: "Hoy" })).toHaveAttribute("aria-pressed", "false");

    await userEvent.selectOptions(await screen.findByLabelText("Caja"), "2");
    expect(urls(fetch)).toContain("/api/reports/sales/?from=2026-01-05&to=2026-01-05&register=2");
  });

  it("productos: más vendidos y sin movimiento", async () => {
    mockApi(base);
    render(<Reports />);
    await userEvent.click(screen.getByRole("button", { name: "Productos" }));

    expect(await screen.findByRole("table", { name: "Más vendidos por cantidad" })).toHaveTextContent(/Tornillo 1\/4.*100 und/);
    expect(screen.getByRole("table", { name: "Más vendidos por valor" })).toHaveTextContent(/Pintura.*600\.000/);
    expect(screen.getByRole("table", { name: "Sin movimiento (1)" })).toHaveTextContent(/Lija 80.*12,5 und/);
  });

  it("arqueos: diferencia, faltantes y notas", async () => {
    mockApi(base);
    render(<Reports />);
    await userEvent.click(screen.getByRole("button", { name: "Arqueos" }));

    const table = await screen.findByRole("table", { name: "Turnos cerrados en el período" });
    const shift = within(table).getByRole("row", { name: /CAJA1/ });
    expect(shift).toHaveTextContent(/124\.100.*200\.000.*274\.100.*272\.100.*-\s?\$?\s?2\.000/);
    expect(shift).toHaveTextContent("Faltó un billete");
    expect(screen.getByText("Faltantes").parentElement).toHaveTextContent(/2\.000/);
  });

  it("sin reports.costs no aparecen inventario valorizado ni márgenes", async () => {
    mockApi(base);
    render(<Reports />);
    await screen.findByText("Venta neta");
    expect(screen.queryByRole("button", { name: "Márgenes" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Inventario valorizado" })).not.toBeInTheDocument();
  });

  it("con reports.costs: inventario sin período y márgenes con aviso de costo estimado", async () => {
    const me = { id: 1, username: "admin", first_name: "", last_name: "", roles: ["Administrador"], permissions: ["reports.view", "reports.costs"], must_change_password: false };
    const fetch = mockApi({
      ...base,
      "/api/auth/csrf/": () => new Response(null, { status: 204 }),
      "/api/auth/me/": () => json(me),
    });
    render(<AuthProvider><Reports /></AuthProvider>);

    await userEvent.click(await screen.findByRole("button", { name: "Inventario valorizado" }));
    const inv = await screen.findByRole("table", { name: "Por producto" });
    expect(within(inv).getByRole("row", { name: /MAR-16/ })).toHaveTextContent(/19\.000.*76\.000.*Bajo el mínimo \(5\)/);
    expect(within(inv).getByRole("row", { name: /PIN-VIN-B/ })).toHaveTextContent(/—.*Negativo/);
    expect(urls(fetch)).toContain("/api/reports/inventory/");
    expect(screen.getByLabelText("Caja")).toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: "Márgenes" }));
    expect(await screen.findByText(/costo estimado/)).toBeInTheDocument();
    expect(screen.getByText("Margen %").parentElement).toHaveTextContent("18,5 %");
    expect(screen.getByRole("table", { name: "Por producto" })).toHaveTextContent(/Martillo.*estimado.*36\.235.*19,2 %/);
  });

  it("descarga el CSV del reporte que se está viendo", async () => {
    mockApi(base);
    const blobs: Blob[] = [];
    const downloads: string[] = [];
    vi.stubGlobal("URL", Object.assign(URL, {
      createObjectURL: vi.fn((blob: Blob) => { blobs.push(blob); return "blob:reporte"; }),
      revokeObjectURL: vi.fn(),
    }));
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      downloads.push(this.download);
    });
    render(<Reports />);
    const button = screen.getByRole("button", { name: "Descargar CSV" });
    expect(button).toBeDisabled(); // todavía no hay datos
    await userEvent.click(screen.getByRole("button", { name: "Arqueos" }));
    await screen.findByRole("table", { name: "Turnos cerrados en el período" });

    await userEvent.click(button);
    expect(downloads).toEqual([`reporte-arqueos_${today}.csv`]);
    const text = await blobs[0].text();
    expect(text).toContain("CAJA1;laura.caja;");
    expect(text).toContain("Faltantes;2000,00");
    click.mockRestore();
  });

  it("muestra el error del servidor", async () => {
    mockApi({ ...base, "/api/reports/sales/": () => json({ period: "El período puede tener como máximo un año." }, 400) });
    render(<Reports />);
    expect(await screen.findByRole("alert")).toHaveTextContent("máximo un año");
  });
});
