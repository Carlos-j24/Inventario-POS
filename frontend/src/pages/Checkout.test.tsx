import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Product } from "../api";
import { Checkout } from "./Pos";

const hammer: Product = {
  id: 2, sku: "MAR-16", name: "Martillo 16 oz", category: "Herramientas", base_unit: "und",
  barcode: null, sale_price: "28000.00", tax_rate: "19", allows_fractions: false, min_stock: "5", units: [],
};

function mockFetch(response: unknown, status = 201) {
  const fn = vi.fn().mockResolvedValue(new Response(JSON.stringify(response), { status }));
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => vi.unstubAllGlobals());

describe("Checkout", () => {
  const props = {
    shiftId: 7,
    lines: [{ key: "a", product: hammer, unit: "und", quantity: 3 }],
    totalCents: 8400000,
    onCancel: () => {},
  };

  it("envía pago mixto con el turno y un client_uuid, y muestra las vueltas", async () => {
    const fetch = mockFetch({ id: 1, number: "V-000001", total: "84000.00", payments: [] });
    const onPaid = vi.fn();
    render(<Checkout {...props} onPaid={onPaid} />);

    await userEvent.type(screen.getByLabelText("Tarjeta"), "60000");
    await userEvent.type(screen.getByLabelText("Efectivo"), "30000");
    expect(screen.getByText(/Vueltas/)).toHaveTextContent("6.000");

    await userEvent.click(screen.getByRole("button", { name: "Confirmar pago" }));
    const body = JSON.parse(fetch.mock.calls[0][1].body);
    expect(body.shift).toBe(7);
    expect(body.client_uuid).toMatch(/^[0-9a-f-]{36}$/);
    expect(body.lines).toEqual([{ product: 2, unit: "und", quantity: "3" }]);
    expect(body.payments).toEqual([
      { method: "CASH", amount: "30000.00", reference: "" },
      { method: "CARD", amount: "60000.00", reference: "" },
    ]);
    expect(onPaid).toHaveBeenCalled();
  });

  it("no deja confirmar si falta dinero", async () => {
    mockFetch({});
    render(<Checkout {...props} onPaid={() => {}} />);
    await userEvent.type(screen.getByLabelText("Efectivo"), "50000");
    expect(screen.getByText(/Faltan/)).toHaveTextContent("34.000");
    expect(screen.getByRole("button", { name: "Confirmar pago" })).toBeDisabled();
  });

  it("reintentar tras un error del servidor reutiliza el mismo client_uuid", async () => {
    const fetch = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: "Error de red" }), { status: 503 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: 1, number: "V-1", total: "84000", payments: [] }), { status: 201 }));
    vi.stubGlobal("fetch", fetch);
    render(<Checkout {...props} onPaid={() => {}} />);
    await userEvent.click(screen.getAllByRole("button", { name: "Exacto" })[0]); // efectivo exacto
    await userEvent.click(screen.getByRole("button", { name: "Confirmar pago" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Error de red");
    await userEvent.click(screen.getByRole("button", { name: "Confirmar pago" }));
    const first = JSON.parse(fetch.mock.calls[0][1].body).client_uuid;
    const second = JSON.parse(fetch.mock.calls[1][1].body).client_uuid;
    expect(second).toBe(first);
  });
});
