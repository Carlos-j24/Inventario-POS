import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { Product } from "../api";
import ProductSearch from "./ProductSearch";

const oil: Product = {
  id: 1, sku: "ACE-20W50", name: "Aceite 20W50", category: "Lubricantes", base_unit: "und", barcode: null,
  sale_price: "30000.00", tax_rate: "19", allows_fractions: false, min_stock: "2", units: [],
};
const wash: Product = { ...oil, id: 2, sku: "LAV-150", name: "Lavado moto", category: "Lavadero", sale_price: "12000.00", is_service: true };

describe("ProductSearch", () => {
  it("marca los servicios en los resultados (spec 010)", async () => {
    const onPick = vi.fn();
    render(<ProductSearch products={[oil, wash]} onPick={onPick} />);
    await userEvent.type(screen.getByLabelText("Buscar producto"), "a");
    expect(screen.getByRole("button", { name: /Lavado moto/ })).toHaveTextContent("LAV-150 · $ 12.000/und · servicio");
    expect(screen.getByRole("button", { name: /Aceite/ })).not.toHaveTextContent("servicio");
    await userEvent.click(screen.getByRole("button", { name: /Lavado moto/ }));
    expect(onPick).toHaveBeenCalledWith(wash, "und"); // la caja lo cobra como cualquier producto
  });
});
