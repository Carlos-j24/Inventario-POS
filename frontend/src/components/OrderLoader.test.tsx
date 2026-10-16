import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Order } from "../api";
import OrderLoader from "./OrderLoader";

const base: Order = {
  id: 9, code: 4193, business_date: "2026-10-16", status: "PENDING", salesperson: "andres",
  total: "96000.00", created_at: "", sale_number: null,
  lines: [{ id: 1, product: 2, sku: "MAR-16", name: "Martillo", unit: "und", quantity: "2.000", unit_price: "28000.00", total: "56000.00" }],
};

function respond(body: unknown, status = 200) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status })));
}

afterEach(() => vi.unstubAllGlobals());

async function load(code: string) {
  await userEvent.type(screen.getByLabelText("Código de pedido"), code);
  await userEvent.click(screen.getByRole("button", { name: "Cargar pedido" }));
}

describe("OrderLoader", () => {
  it("carga un pedido pendiente por su código", async () => {
    respond(base);
    const onLoad = vi.fn();
    render(<OrderLoader onLoad={onLoad} />);
    await load("4193");
    expect(onLoad).toHaveBeenCalledWith(base);
    expect(vi.mocked(fetch).mock.calls[0][0]).toBe("/api/orders/code/4193/");
  });

  it.each([
    [{ ...base, status: "PAID", sale_number: "V-000009" }, "ya fue cobrado (venta V-000009)"],
    [{ ...base, status: "CANCELLED" }, "fue cancelado"],
    [{ ...base, status: "EXPIRED" }, "venció"],
  ])("explica por qué no se cobra un pedido %#", async (order, message) => {
    respond(order);
    const onLoad = vi.fn();
    render(<OrderLoader onLoad={onLoad} />);
    await load("4193");
    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(onLoad).not.toHaveBeenCalled();
  });

  it("código que no existe hoy", async () => {
    respond({ detail: "No encontrado." }, 404);
    render(<OrderLoader onLoad={vi.fn()} />);
    await load("1111");
    expect(await screen.findByRole("alert")).toHaveTextContent("No hay un pedido de hoy con el código 1111");
  });

  it("solo acepta 4 dígitos y no consulta si el código está incompleto", async () => {
    respond(base);
    render(<OrderLoader onLoad={vi.fn()} />);
    await load("41a9"); // la letra se ignora: quedan 3 dígitos
    expect(screen.getByLabelText("Código de pedido")).toHaveValue("419");
    expect(await screen.findByRole("alert")).toHaveTextContent("4 dígitos");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("deja elegir entre los pendientes de hoy", async () => {
    respond([base, { ...base, id: 10, code: 5555, salesperson: "otra" }]);
    const onLoad = vi.fn();
    render(<OrderLoader onLoad={onLoad} />);
    await userEvent.click(screen.getByRole("button", { name: "Pedidos pendientes" }));
    await userEvent.click(await screen.findByText("5555"));
    expect(onLoad).toHaveBeenCalledWith(expect.objectContaining({ code: 5555 }));
  });
});
