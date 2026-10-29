import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { QuoteDetail, QuoteLine } from "../api";
import QuotePrint from "./QuotePrint";

const line = (over: Partial<QuoteLine>): QuoteLine => ({
  id: 1, product: 1, sku: "CEM-50", name: "Cemento gris 50 kg", unit: "bulto", quantity: "20.000", unit_price: "34500.00", tax_rate: "19",
  vat_excluded: false, total: "690000.00", subtotal: "579831.93", tax: "110168.07", active: true, in_orders: "0.000", charged: "0.000", remaining: "20.000", ...over,
});

const quote: QuoteDetail = {
  id: 1, number: "COT-000001", customer: "Constructora Los Pinos", customer_phone: "3001234567", status: "VALID", status_label: "Vigente",
  valid_until: "2026-10-30", total: "1066000.00", created_by: "andres.ventas", created_at: "2026-10-22T15:30:00Z", lines_count: 3,
  customer_id: 7, customer_document: "NIT 900123456-8", note: "Entrega en obra, calle 12", void_note: "", voided_by: null, duplicated_from: null,
  lines: [
    line({}),
    line({ id: 2, sku: "CAB-12", name: "Cable THHN calibre 12", unit: "rollo", quantity: "1.000", unit_price: "320000.00", total: "320000.00" }),
    line({ id: 3, sku: "ARE-B", name: "Arena de pega", quantity: "6.000", unit_price: "9333.33", total: "56000.00", tax_rate: "0", vat_excluded: true }),
  ],
  subtotal: "905882.36", tax: "160117.64", taxes: [
    { rate: "19", base: "849882.36", tax: "160117.64" },
    { rate: "excluido", base: "56000.00", tax: "0.00" },
  ],
  orders: [], can_convert: true,
  business: { name: "Ferretería El Tornillo S.A.S.", trade_name: "El Tornillo", nit: "900555111-2", address: "Cra 7 # 10-20", city: "Florencia", phone: "6084351234", email: "ventas@eltornillo.co", tax_regime: "" },
};

describe("hoja de la cotización", () => {
  it("lleva los datos del negocio, el número, las fechas y el cliente", () => {
    render(<QuotePrint quote={quote} />);
    const sheet = screen.getByRole("article", { name: "Hoja de la cotización" });
    expect(within(sheet).getByRole("img", { name: "Logo del negocio" })).toHaveAttribute("src", "/brand/logo.png");
    expect(sheet.querySelector(".quote-sheet-business")).toHaveTextContent(/^El Tornillo$/); // el nombre comercial, en grande
    expect(sheet).toHaveTextContent("Ferretería El Tornillo S.A.S.");
    expect(sheet).toHaveTextContent("NIT 900555111-2");
    expect(sheet).toHaveTextContent("Cra 7 # 10-20, Florencia");
    expect(sheet).toHaveTextContent("Tel. 6084351234 · ventas@eltornillo.co");
    expect(sheet).toHaveTextContent(/Cotización\s*COT-000001\s*22 de octubre de 2026/);
    expect(sheet).toHaveTextContent(/Constructora Los Pinos\s*NIT 900123456-8\s*Tel\. 3001234567/);
    expect(sheet).toHaveTextContent(/Válida hasta\s*30 de octubre de 2026\s*Atendió\s*andres\.ventas/);
    expect(sheet).toHaveTextContent("Nota: Entrega en obra, calle 12");
    expect(within(sheet).queryByRole("note")).not.toBeInTheDocument(); // vigente: sin aviso
  });

  it("las líneas con su IVA, el IVA por tarifa y los totales", () => {
    render(<QuotePrint quote={quote} />);
    const rows = within(screen.getByRole("table", { name: "Productos cotizados" })).getAllByRole("row").slice(1);
    const text = (r: HTMLElement) => r.textContent!.replace(/\s/g, " "); // el $ lleva un espacio duro
    expect(rows.map(text)).toEqual([
      "20bultoCemento gris 50 kg (CEM-50)19 %$ 34.500$ 690.000",
      "1rolloCable THHN calibre 12 (CAB-12)19 %$ 320.000$ 320.000",
      "6bultoArena de pega (ARE-B)Excluido$ 9.333,33$ 56.000",
    ]);
    const taxes = within(screen.getByRole("table", { name: "IVA por tarifa" })).getAllByRole("row").slice(1);
    expect(taxes.map(text)).toEqual(["19 %$ 849.882,36$ 160.117,64", "Excluido$ 56.000$ 0"]);
    expect(screen.getByRole("table", { name: "Totales" })).toHaveTextContent(/Subtotal\$ 905\.882,36IVA\$ 160\.117,64Total\$ 1\.066\.000/);
    expect(screen.getByText(/Precios con IVA incluido, válidos hasta el 30 de octubre de 2026/)).toBeInTheDocument();
    expect(screen.getByText(/presente el número COT-000001/)).toBeInTheDocument();
  });

  it("al imprimir usa hoja carta, no el rollo de 80 mm del tiquete", () => {
    const { container } = render(<QuotePrint quote={quote} />);
    expect(container.querySelector("style")?.textContent).toBe("@media print { @page { size: letter portrait; margin: 14mm; } }");
  });

  it.each([
    ["VOIDED", "ANULADA: esta cotización ya no es válida."],
    ["EXPIRED", "VENCIDA: esta cotización ya no es válida."],
  ] as const)("una %s lo dice en grande", (status, text) => {
    render(<QuotePrint quote={{ ...quote, status }} />);
    expect(screen.getByRole("note")).toHaveTextContent(text);
  });

  it("sin nombre comercial ni datos opcionales no deja huecos", () => {
    const bare = { ...quote, customer_document: null, customer_phone: "", note: "",
      business: { ...quote.business, trade_name: "", nit: "", address: "", city: "", phone: "", email: "" } };
    render(<QuotePrint quote={bare} />);
    const sheet = screen.getByRole("article", { name: "Hoja de la cotización" });
    expect(sheet.querySelector(".quote-sheet-business")).toHaveTextContent("Ferretería El Tornillo S.A.S.");
    expect(sheet).not.toHaveTextContent(/NIT|Tel\.|Nota:/);
  });
});
