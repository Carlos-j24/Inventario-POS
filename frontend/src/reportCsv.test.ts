import { describe, expect, it } from "vitest";

import { inventory, margins, products, sales, shifts } from "./pages/reportFixtures";
import { csvDateTime, reportCsv } from "./reportCsv";

const week = { from: "2026-10-12", to: "2026-10-17" };
const lines = (content: string) => content.slice(content.charCodeAt(0) === 0xfeff ? 1 : 0).split("\r\n");

describe("reportCsv", () => {
  it("ventas: totales y desgloses con las cifras de la pantalla", () => {
    const { filename, content } = reportCsv("sales", sales, week, "2026-10-17");
    expect(filename).toBe("reporte-ventas_2026-10-12_2026-10-17.csv");
    const l = lines(content);
    expect(l.slice(0, 3)).toEqual(["Totales", "Concepto;Valor", "Ventas;8"]);
    expect(l).toContain("Venta neta;1200100,00");
    expect(l).toContain("Ticket promedio;157012,50");
    expect(l).toContain("IVA neto;191612,61");
    expect(l).toContain("Día;Ventas;Total;Devoluciones;Neto");
    expect(l).toContain("2026-10-16;4;276000,00;56000,00;220000,00");
    expect(l).toContain("CAJA1;7;1200100,00;28000,00;1172100,00");
    expect(l).toContain("andres.ventas;1;68000,00;28000,00;40000,00");
    expect(l).toContain("Efectivo;960100,00;56000,00;904100,00");
  });

  it("un solo día lleva una sola fecha en el nombre", () => {
    expect(reportCsv("sales", sales, { from: "2026-10-16", to: "2026-10-16" }, "2026-10-17").filename)
      .toBe("reporte-ventas_2026-10-16.csv");
  });

  it("productos: rankings y sin movimiento", () => {
    const l = lines(reportCsv("products", products, week, "2026-10-17").content);
    expect(l).toContain("Más vendidos por cantidad");
    expect(l).toContain("TOR-1/4;Tornillo 1/4;und;100,000;1;15000,00;12605,04");
    expect(l).toContain("PIN-VIN-B;Pintura vinilo blanca;gal;10,000;3;600000,00;504201,68");
    expect(l).toContain("LIJ-80;Lija 80;und;12,500");
  });

  it("arqueos: hora de Bogotá, diferencia negativa y totales", () => {
    const { filename, content } = reportCsv("shifts", shifts, week, "2026-10-17");
    expect(filename).toBe("reporte-arqueos_2026-10-12_2026-10-17.csv");
    const l = lines(content);
    expect(l).toContain(
      "CAJA1;laura.caja;2026-10-16 08:00;laura.caja;2026-10-16 18:00;4;150000,00;124100,00;200000,00;0,00;274100,00;272100,00;-2000,00;Faltó un billete",
    );
    expect(l).toContain("Faltantes;2000,00");
    expect(l).toContain("Diferencia neta;-2000,00");
  });

  it("inventario: foto de hoy, sin costo cuando no hay existencias positivas, y fila de total", () => {
    const { filename, content } = reportCsv("inventory", inventory, week, "2026-10-17");
    expect(filename).toBe("reporte-inventario_2026-10-17.csv");
    const l = lines(content);
    expect(l[0]).toBe("SKU;Producto;Unidad;Existencias;Mínimo;Costo promedio;Valor;Bajo el mínimo;Negativo");
    expect(l).toContain("MAR-16;Martillo 16 oz;und;4,000;5,000;19000,0000;76000,00;Sí;No");
    expect(l).toContain("PIN-VIN-B;Pintura vinilo blanca;gal;-2,000;0,000;;0,00;No;Sí");
    expect(l).toContain("Total;;;;;;1373350,00;1;1");
    const totals = { ...inventory.totals, below_min: 3, negative: 1 };
    expect(lines(reportCsv("inventory", { ...inventory, totals }, week, "2026-10-17").content))
      .toContain("Total;;;;;;1373350,00;3;1"); // bajo el mínimo y luego negativos
  });

  it("márgenes: porcentaje, costo estimado y total", () => {
    const l = lines(reportCsv("margins", margins, week, "2026-10-17").content);
    expect(l).toContain("MAR-16;Martillo 16 oz;188235,28;152000,00;36235,28;19,2;Sí");
    expect(l).toContain("Total;;1008487,39;822150,00;186337,39;18,5;Sí");
  });

  it("márgenes sin venta: porcentaje vacío", () => {
    const empty = { ...margins, rows: [], totals: { ...margins.totals, net_sales: "0.00", margin_pct: null, cost_estimated: false } };
    expect(lines(reportCsv("margins", empty, week, "2026-10-17").content)).toContain("Total;;0,00;822150,00;186337,39;;No");
  });
});

describe("csvDateTime", () => {
  it("usa la hora de Bogotá, sin importar la zona del equipo", () => {
    expect(csvDateTime("2026-10-17T03:30:00Z")).toBe("2026-10-16 22:30");
  });
});
