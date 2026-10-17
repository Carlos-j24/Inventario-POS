import { describe, expect, it } from "vitest";

import { csvCell, num, toCsv } from "./csv";

const BOM = String.fromCharCode(0xfeff);

describe("csvCell", () => {
  it("números con coma decimal y sin separador de miles", () => {
    expect(csvCell(num("1200100.00"))).toBe("1200100,00");
    expect(csvCell(num("-2000.00"))).toBe("-2000,00"); // un número negativo no se toca
    expect(csvCell(num("12.500"))).toBe("12,500");
    expect(csvCell(8)).toBe("8");
    expect(csvCell(null)).toBe("");
  });

  it("entre comillas si el texto trae ; comillas o saltos de línea", () => {
    expect(csvCell("Tornillo 1/4")).toBe("Tornillo 1/4");
    expect(csvCell("Lija; grano 80")).toBe('"Lija; grano 80"');
    expect(csvCell('Tubo 1/2"')).toBe('"Tubo 1/2"""');
    expect(csvCell("Faltó\nun billete")).toBe('"Faltó\nun billete"');
  });

  it("neutraliza textos que Excel tomaría como fórmula", () => {
    expect(csvCell("=HYPERLINK(\"x\")")).toBe("\"'=HYPERLINK(\"\"x\"\")\"");
    expect(csvCell("+57 300")).toBe("'+57 300");
    expect(csvCell("-descuento")).toBe("'-descuento");
    expect(csvCell("@admin")).toBe("'@admin");
  });
});

describe("toCsv", () => {
  it("BOM, ; entre columnas, CRLF y una línea en blanco entre tablas", () => {
    const csv = toCsv([
      { title: "Por día", head: ["Día", "Neto"], rows: [["2026-10-15", num("980100.00")]] },
      { head: ["Medio", "Neto"], rows: [["Efectivo", num("904100.00")]] },
    ]);
    expect(csv).toBe(BOM + "Por día\r\nDía;Neto\r\n2026-10-15;980100,00\r\n\r\nMedio;Neto\r\nEfectivo;904100,00\r\n");
  });
});
