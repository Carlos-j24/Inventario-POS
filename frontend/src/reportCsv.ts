// CSV de cada reporte, con las mismas cifras que la pantalla (salen de la misma respuesta de la API).
import type {
  InventoryReport,
  MarginsReport,
  ProductReportRow,
  ProductsReport,
  ReportRow,
  SalesReport,
  ShiftsReport,
} from "./api";
import { num, toCsv, type Cell, type Section } from "./csv";
import type { Period } from "./reports";

const yesNo = (value: boolean) => (value ? "Sí" : "No");

// Fecha y hora del negocio (Bogotá) en un formato que Excel reconoce: 2026-10-16 18:00.
const bogota = new Intl.DateTimeFormat("sv-SE", {
  timeZone: "America/Bogota", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
});
export const csvDateTime = (iso: string) => bogota.format(new Date(iso));

function breakdown<T extends ReportRow>(title: string, label: string, rows: T[], name: (row: T) => string): Section {
  return {
    title,
    head: [label, "Ventas", "Total", "Devoluciones", "Neto"],
    rows: rows.map((r) => [name(r), r.sales_count, num(r.total), num(r.returns), num(r.net)]),
  };
}

function salesCsv(r: SalesReport): Section[] {
  const t = r.totals;
  const totals: [string, Cell][] = [
    ["Ventas", t.sales_count],
    ["Total", num(t.total)],
    ["Subtotal sin IVA", num(t.subtotal)],
    ["IVA", num(t.tax)],
    ["Devoluciones", num(t.returns_total)],
    ["Devoluciones sin IVA", num(t.returns_subtotal)],
    ["IVA devuelto", num(t.returns_tax)],
    ["Venta neta", num(t.net_total)],
    ["Venta neta sin IVA", num(t.net_subtotal)],
    ["IVA neto", num(t.net_tax)],
    ["Ticket promedio", num(t.average_ticket)],
  ];
  return [
    { title: "Totales", head: ["Concepto", "Valor"], rows: totals },
    breakdown("Por día", "Día", r.by_day, (x) => x.day),
    breakdown("Por caja", "Caja", r.by_register, (x) => x.register),
    breakdown("Por vendedor", "Vendedor", r.by_salesperson, (x) => x.salesperson),
    {
      title: "Por medio de pago",
      head: ["Medio", "Cobros", "Reembolsos", "Neto"],
      rows: r.by_method.map((m) => [m.label, num(m.payments), num(m.refunds), num(m.net)]),
    },
  ];
}

function ranking(title: string, rows: ProductReportRow[]): Section {
  return {
    title,
    head: ["SKU", "Producto", "Unidad", "Cantidad", "Ventas", "Total", "Subtotal sin IVA"],
    rows: rows.map((p) => [p.sku, p.name, p.unit, num(p.quantity), p.sales_count, num(p.total), num(p.subtotal)]),
  };
}

function productsCsv(r: ProductsReport): Section[] {
  return [
    ranking("Más vendidos por cantidad", r.by_quantity),
    ranking("Más vendidos por valor", r.by_value),
    {
      title: "Sin movimiento",
      head: ["SKU", "Producto", "Unidad", "Existencias"],
      rows: r.not_moved.map((p) => [p.sku, p.name, p.unit, num(p.stock)]),
    },
  ];
}

function shiftsCsv(r: ShiftsReport): Section[] {
  const t = r.totals;
  return [
    {
      title: "Turnos cerrados",
      head: [
        "Caja", "Abrió", "Apertura", "Cerró", "Cierre", "Ventas", "Base",
        "Efectivo", "Tarjeta", "Transferencia", "Esperado", "Contado", "Diferencia", "Notas",
      ],
      rows: r.rows.map((s) => [
        s.register, s.opened_by, csvDateTime(s.opened_at), s.closed_by, csvDateTime(s.closed_at), s.sales_count,
        num(s.opening_float), num(s.by_method.CASH), num(s.by_method.CARD), num(s.by_method.TRANSFER),
        num(s.expected_cash), num(s.counted_cash), num(s.difference), s.notes,
      ]),
    },
    {
      title: "Totales",
      head: ["Concepto", "Valor"],
      rows: [
        ["Turnos", t.shifts],
        ["Esperado", num(t.expected_cash)],
        ["Contado", num(t.counted_cash)],
        ["Diferencia neta", num(t.difference)],
        ["Faltantes", num(t.shortage)],
        ["Sobrantes", num(t.overage)],
      ],
    },
  ];
}

function inventoryCsv(r: InventoryReport): Section[] {
  return [{
    head: ["SKU", "Producto", "Unidad", "Existencias", "Mínimo", "Costo promedio", "Valor", "Bajo el mínimo", "Negativo"],
    rows: [
      ...r.rows.map((p): Cell[] => [
        p.sku, p.name, p.unit, num(p.stock), num(p.min_stock),
        p.average_cost == null ? null : num(p.average_cost), num(p.value), yesNo(p.below_min), yesNo(p.negative),
      ]),
      ["Total", null, null, null, null, null, num(r.totals.value), r.totals.below_min, r.totals.negative],
    ],
  }];
}

function marginsCsv(r: MarginsReport): Section[] {
  const t = r.totals;
  return [{
    head: ["SKU", "Producto", "Venta neta sin IVA", "Costo", "Margen", "Margen %", "Costo estimado"],
    rows: [
      ...r.rows.map((p): Cell[] => [
        p.sku, p.name, num(p.net_sales), num(p.cost), num(p.margin),
        p.margin_pct == null ? null : num(p.margin_pct), yesNo(p.cost_estimated),
      ]),
      ["Total", null, num(t.net_sales), num(t.cost), num(t.margin), t.margin_pct == null ? null : num(t.margin_pct), yesNo(t.cost_estimated)],
    ],
  }];
}

const BUILDERS: Record<string, { name: string; build: (data: never) => Section[] }> = {
  sales: { name: "ventas", build: salesCsv },
  products: { name: "productos", build: productsCsv },
  shifts: { name: "arqueos", build: shiftsCsv },
  inventory: { name: "inventario", build: inventoryCsv },
  margins: { name: "margenes", build: marginsCsv },
};

/** Nombre y contenido del CSV de un reporte. El inventario es una foto: lleva la fecha de hoy. */
export function reportCsv(report: string, data: unknown, period: Period, today: string): { filename: string; content: string } {
  const { name, build } = BUILDERS[report];
  const dates = report === "inventory" ? today : period.from === period.to ? period.from : `${period.from}_${period.to}`;
  return { filename: `reporte-${name}_${dates}.csv`, content: toCsv(build(data as never)) };
}
