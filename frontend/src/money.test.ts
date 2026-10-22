import { describe, expect, it } from "vitest";

import { formatMoney } from "./money";

const show = (cents: number) => formatMoney(cents).replace(/\s/g, " "); // el $ lleva un espacio duro

describe("formatMoney", () => {
  it("pesos enteros sin decimales", () => {
    expect([show(3450000), show(0), show(-200000)]).toEqual(["$ 34.500", "$ 0", "-$ 2.000"]);
  });

  it("con centavos, siempre dos cifras (lo encontró la hoja de la cotización)", () => {
    expect([show(32773110), show(6226890), show(933333), show(5), show(-150)]).toEqual([
      "$ 327.731,10", "$ 62.268,90", "$ 9.333,33", "$ 0,05", "-$ 1,50",
    ]);
  });
});
