import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { TicketData } from "../api";
import SalePrint, { SalePrintDialog } from "./SalePrint";
import TicketDialog from "./TicketDialog";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

const sale: TicketData = {
  business: { name: "Moto Repuestos y Lavadero Arias", trade_name: "", nit: "900123456-7", address: "Cra 1", city: "Florencia", phone: "3100000000", email: "", tax_regime: "" },
  title: "Comprobante de venta", code: null, status: null, document_id: null, sale_number: "V-000121",
  issued_at: "2026-11-03T20:15:00Z", register: "CAJA1", cashier: "laura.caja",
  customer: { name: "Jorge Ramírez", document: "Cédula de ciudadanía 79123456", phone: "3001234567" },
  work_order: { number: "OT-000011", plate: "JKL90B", motorcycle: "Suzuki GN 125", mileage_in: 49100 },
  lines: [
    { name: "Aceite 4T 20W50 x 1 L", sku: "ACE-20W50", quantity: "1.000", unit: "und", unit_price: "32000.00", total: "32000.00", tax_rate: "19" },
    { name: "Mano de obra de taller", sku: "MO-TALLER", quantity: "1.000", unit: "und", unit_price: "20000.00", total: "20000.00", tax_rate: "19" },
  ],
  subtotal: "43697.48", tax: "8302.52", total: "52000.00", taxes: [{ rate: "19", base: "43697.48", tax: "8302.52" }],
  payments: [{ label: "Efectivo", amount: "60000.00" }], change: "8000.00",
  cude: null, qr_svg: null, resolution: null, notes: ["Sin documento electrónico: la facturación electrónica no está activa."],
};

function mockApi(routes: Record<string, () => Response>) {
  const fn = vi.fn((url: string, init?: RequestInit) => {
    const route = routes[`${init?.method ?? "GET"} ${url}`];
    return route ? Promise.resolve(route()) : Promise.reject(new Error(`ruta no simulada: ${url}`));
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => vi.unstubAllGlobals());

describe("comprobante en hoja carta (spec 013)", () => {
  it("lleva el logo, los datos del negocio, el cliente, la moto, las líneas, el IVA, el pago y el total", () => {
    render(<SalePrint data={sale} />);
    const sheet = screen.getByRole("article", { name: "Comprobante de venta" });
    expect(within(sheet).getByRole("img", { name: "Logo del negocio" })).toBeInTheDocument();
    expect(sheet).toHaveTextContent("Moto Repuestos y Lavadero AriasNIT 900123456-7Cra 1, FlorenciaTel. 3100000000");
    expect(sheet).toHaveTextContent("Comprobante de ventaV-000121");
    expect(within(sheet).getByRole("note")).toHaveTextContent("Documento sin validez fiscal");
    expect(sheet).toHaveTextContent("ClienteJorge RamírezCédula de ciudadanía 79123456Tel. 3001234567");
    expect(sheet).toHaveTextContent("MotoJKL90B · Suzuki GN 125Orden OT-000011 · llegó con 49.100 km");
    expect(sheet).toHaveTextContent("Atendiólaura.caja · CAJA1");
    const lines = within(sheet).getByRole("table", { name: "Productos vendidos" });
    expect(within(lines).getAllByRole("row")).toHaveLength(3);
    expect(within(lines).getByRole("row", { name: /Aceite/ })).toHaveTextContent("1undAceite 4T 20W50 x 1 L (ACE-20W50)19 %$ 32.000$ 32.000");
    expect(within(sheet).getByRole("table", { name: "IVA por tarifa" })).toHaveTextContent("19 %$ 43.697,48$ 8.302,52");
    expect(within(sheet).getByRole("table", { name: "Forma de pago" })).toHaveTextContent("Efectivo$ 60.000Vueltas$ 8.000");
    expect(within(sheet).getByRole("table", { name: "Totales" })).toHaveTextContent("Total$ 52.000");
    expect(sheet).toHaveTextContent("no reemplaza la factura electrónica");
    expect(sheet).not.toHaveTextContent("Documento electrónico de esta venta");
  });

  it("sin cliente es consumidor final; sin orden no hay moto; con documento electrónico lo nombra", () => {
    render(<SalePrint data={{ ...sale, customer: null, work_order: null, code: "CJ11", title: "Documento equivalente electrónico POS", change: "0.00" }} />);
    const sheet = screen.getByRole("article", { name: "Comprobante de venta" });
    expect(sheet).toHaveTextContent("ClienteConsumidor final");
    expect(sheet).not.toHaveTextContent("Orden OT-");
    expect(sheet).not.toHaveTextContent("Vueltas");
    expect(sheet).toHaveTextContent("Documento electrónico de esta venta: Documento equivalente electrónico POS CJ11.");
  });

  it("el diálogo pide la venta, imprime y se cierra", async () => {
    mockApi({ "GET /api/invoicing/ticket/121/": () => json(sale) });
    const print = vi.fn();
    vi.stubGlobal("print", print);
    const onClose = vi.fn();
    render(<SalePrintDialog saleId={121} onClose={onClose} />);
    const dialog = screen.getByRole("dialog", { name: "Imprimir comprobante" });
    expect(dialog.parentElement).toBe(document.body); // portal: al imprimir se oculta lo demás
    expect(within(dialog).getByRole("button", { name: "Imprimir" })).toBeDisabled();
    await within(dialog).findByRole("article", { name: "Comprobante de venta" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Imprimir" }));
    expect(print).toHaveBeenCalledOnce();
    await userEvent.click(within(dialog).getByRole("button", { name: "Cerrar" }));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("desde el tiquete de la caja se abre la hoja carta; un tiquete sin conexión no la ofrece", async () => {
    mockApi({ "GET /api/invoicing/ticket/121/": () => json(sale) });
    const { unmount } = render(<TicketDialog saleId={121} onClose={() => {}} />);
    await screen.findByText("V-000121", { exact: false });
    await userEvent.click(screen.getByRole("button", { name: "Hoja carta" }));
    const dialog = screen.getByRole("dialog", { name: "Imprimir comprobante" });
    expect(await within(dialog).findByRole("article", { name: "Comprobante de venta" })).toHaveTextContent("Jorge Ramírez");
    await userEvent.click(within(dialog).getByRole("button", { name: "Cerrar" }));
    expect(screen.queryByRole("dialog", { name: "Imprimir comprobante" })).not.toBeInTheDocument();
    unmount();
    render(<TicketDialog data={sale} onClose={() => {}} />);
    expect(screen.queryByRole("button", { name: "Hoja carta" })).not.toBeInTheDocument();
  });
});
