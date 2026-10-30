import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { Product } from "../api";
import CartTable from "./CartTable";

const oil: Product = {
  id: 2, sku: "ACE-20W50", name: "Aceite 20W50", category: "Lubricantes", base_unit: "und",
  barcode: null, sale_price: "32000.00", tax_rate: "19", allows_fractions: false, min_stock: "5", units: [],
};
const lines = [{ key: "o", product: oil, unit: "und", quantity: 1, order: { lineId: 12, max: 1, priceCents: 3200000 } }];

describe("tabla del carrito", () => {
  it("de un pedido de mostrador se bajan cantidades y se quitan líneas", async () => {
    const onChange = vi.fn();
    render(<CartTable lines={lines} onChange={onChange} emptyText="" />);
    expect(screen.getByLabelText("Cantidad de Aceite 20W50")).not.toHaveAttribute("readonly");
    await userEvent.click(screen.getByRole("button", { name: "Quitar Aceite 20W50" }));
    expect(onChange).toHaveBeenCalledWith([]);
  });

  it("de una orden de taller no se cambia nada: se cobra completa (spec 011)", () => {
    render(<CartTable lines={lines} onChange={vi.fn()} emptyText="" locked />);
    expect(screen.getByLabelText("Cantidad de Aceite 20W50")).toHaveAttribute("readonly");
    expect(screen.queryByRole("button", { name: "Quitar Aceite 20W50" })).not.toBeInTheDocument();
  });
});
