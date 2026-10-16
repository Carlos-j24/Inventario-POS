import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CloseShift } from "./Pos";

afterEach(() => vi.unstubAllGlobals());

describe("CloseShift", () => {
  it("no muestra el efectivo esperado antes de contar (arqueo a ciegas)", async () => {
    const shift = {
      id: 3, register: "CAJA1", status: "OPEN", opening_float: "100000.00",
      expected_cash: null, counted_cash: null, difference: null,
      summary: {
        sales: 2,
        by_method: { CASH: "656000.00", CARD: "40000.00", TRANSFER: "56000.00" },
        refunds: { CASH: "0.00", CARD: "0.00", TRANSFER: "0.00" },
        expected_cash: "756000.00",
      },
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(shift), { status: 200 })));
    render(<CloseShift shiftId={3} onCancel={() => {}} onClosed={() => {}} />);

    expect(await screen.findByText("Tarjeta")).toBeInTheDocument();
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/656\.000|756\.000|100\.000/);
  });
});
