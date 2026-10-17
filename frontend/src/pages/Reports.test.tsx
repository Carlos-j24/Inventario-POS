import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { InventoryReport, MarginsReport, ProductsReport, SalesReport, ShiftsReport } from "../api";
import { AuthProvider } from "../auth";
import { presetPeriod } from "../reports";
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

const row = (sales_count: number, total: string, returns: string, net: string) => ({ sales_count, total, returns, net });

const sales: SalesReport = {
  from: "2026-10-15", to: "2026-10-16",
  totals: {
    sales_count: 8, total: "1256100.00", subtotal: "1055546.21", tax: "200553.79",
    returns_total: "56000.00", returns_subtotal: "47058.82", returns_tax: "8941.18",
    net_total: "1200100.00", net_subtotal: "1008487.39", net_tax: "191612.61", average_ticket: "157012.50",
  },
  by_day: [{ day: "2026-10-15", ...row(4, "980100.00", "0.00", "980100.00") }, { day: "2026-10-16", ...row(4, "276000.00", "56000.00", "220000.00") }],
  by_register: [{ register: "CAJA1", ...row(7, "1200100.00", "28000.00", "1172100.00") }],
  by_salesperson: [{ salesperson: "andres.ventas", ...row(1, "68000.00", "28000.00", "40000.00") }],
  by_method: [{ method: "CASH", label: "Efectivo", payments: "960100.00", refunds: "56000.00", net: "904100.00" }],
};

const products: ProductsReport = {
  from: "2026-10-16", to: "2026-10-16",
  by_quantity: [{ product: 6, sku: "TOR-1/4", name: "Tornillo 1/4", unit: "und", sales_count: 1, quantity: "100.000", total: "15000.00", subtotal: "12605.04" }],
  by_value: [{ product: 5, sku: "PIN-VIN-B", name: "Pintura vinilo blanca", unit: "gal", sales_count: 3, quantity: "10.000", total: "600000.00", subtotal: "504201.68" }],
  not_moved: [{ product: 9, sku: "LIJ-80", name: "Lija 80", unit: "und", stock: "12.500" }],
};

const shifts: ShiftsReport = {
  from: "2026-10-16", to: "2026-10-16",
  totals: {
    shifts: 1, expected_cash: "274100.00", counted_cash: "272100.00", difference: "-2000.00", shortage: "2000.00", overage: "0.00",
    by_method: { CASH: "124100.00", CARD: "200000.00", TRANSFER: "0.00" },
  },
  rows: [{
    shift: 3, register: "CAJA1", opened_by: "laura.caja", opened_at: "2026-10-16T13:00:00Z", closed_by: "laura.caja",
    closed_at: "2026-10-16T23:00:00Z", sales_count: 4, opening_float: "150000.00",
    by_method: { CASH: "124100.00", CARD: "200000.00", TRANSFER: "0.00" },
    expected_cash: "274100.00", counted_cash: "272100.00", difference: "-2000.00", notes: "Faltó un billete",
  }],
};

const inventory: InventoryReport = {
  totals: { value: "1373350.00", products: 2, below_min: 1, negative: 1 },
  rows: [
    { product: 2, sku: "MAR-16", name: "Martillo 16 oz", unit: "und", stock: "4.000", min_stock: "5.000", average_cost: "19000.0000", value: "76000.00", below_min: true, negative: false },
    { product: 5, sku: "PIN-VIN-B", name: "Pintura vinilo blanca", unit: "gal", stock: "-2.000", min_stock: "0.000", average_cost: null, value: "0.00", below_min: false, negative: true },
  ],
};

const margins: MarginsReport = {
  from: "2026-10-16", to: "2026-10-16",
  totals: { net_sales: "1008487.39", cost: "822150.00", margin: "186337.39", margin_pct: "18.5", cost_estimated: true },
  rows: [{ product: 2, sku: "MAR-16", name: "Martillo 16 oz", net_sales: "188235.28", cost: "152000.00", margin: "36235.28", margin_pct: "19.2", cost_estimated: true }],
};

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

  it("muestra el error del servidor", async () => {
    mockApi({ ...base, "/api/reports/sales/": () => json({ period: "El período puede tener como máximo un año." }, 400) });
    render(<Reports />);
    expect(await screen.findByRole("alert")).toHaveTextContent("máximo un año");
  });
});
