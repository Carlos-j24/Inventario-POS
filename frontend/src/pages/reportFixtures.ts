// Reportes de ejemplo (cifras de la base de demostración) para los tests de la pantalla y del CSV.
import type { InventoryReport, MarginsReport, ProductsReport, QuotesReport, SalesReport, ShiftsReport } from "../api";

const row = (sales_count: number, total: string, returns: string, net: string) => ({ sales_count, total, returns, net });

export const sales: SalesReport = {
  from: "2026-10-15", to: "2026-10-16",
  totals: {
    sales_count: 8, total: "1256100.00", subtotal: "1055546.21", tax: "200553.79",
    returns_total: "56000.00", returns_subtotal: "47058.82", returns_tax: "8941.18",
    net_total: "1200100.00", net_subtotal: "1008487.39", net_tax: "191612.61", average_ticket: "157012.50",
  },
  by_day: [{ day: "2026-10-15", ...row(4, "980100.00", "0.00", "980100.00") }, { day: "2026-10-16", ...row(4, "276000.00", "56000.00", "220000.00") }],
  by_register: [{ register: "CAJA1", ...row(7, "1200100.00", "28000.00", "1172100.00") }],
  by_salesperson: [{ salesperson: "andres.ventas", ...row(1, "68000.00", "28000.00", "40000.00") }],
  by_method: [{ method: "CASH", label: "Efectivo", payments: "960100.00", refunds: "56000.00", net: "904100.00" }],
};

export const products: ProductsReport = {
  from: "2026-10-16", to: "2026-10-16",
  by_quantity: [{ product: 6, sku: "TOR-1/4", name: "Tornillo 1/4", unit: "und", sales_count: 1, quantity: "100.000", total: "15000.00", subtotal: "12605.04" }],
  by_value: [{ product: 5, sku: "PIN-VIN-B", name: "Pintura vinilo blanca", unit: "gal", sales_count: 3, quantity: "10.000", total: "600000.00", subtotal: "504201.68" }],
  not_moved: [{ product: 9, sku: "LIJ-80", name: "Lija 80", unit: "und", stock: "12.500" }],
};

export const shifts: ShiftsReport = {
  from: "2026-10-16", to: "2026-10-16",
  totals: {
    shifts: 1, expected_cash: "274100.00", counted_cash: "272100.00", difference: "-2000.00", shortage: "2000.00", overage: "0.00",
    by_method: { CASH: "124100.00", CARD: "200000.00", TRANSFER: "0.00" },
  },
  rows: [{
    shift: 3, register: "CAJA1", opened_by: "laura.caja", opened_at: "2026-10-16T13:00:00Z", closed_by: "laura.caja",
    closed_at: "2026-10-16T23:00:00Z", sales_count: 4, opening_float: "150000.00",
    by_method: { CASH: "124100.00", CARD: "200000.00", TRANSFER: "0.00" },
    expected_cash: "274100.00", counted_cash: "272100.00", difference: "-2000.00", notes: "Faltó un billete",
  }],
};

export const inventory: InventoryReport = {
  totals: { value: "1373350.00", products: 2, below_min: 1, negative: 1 },
  rows: [
    { product: 2, sku: "MAR-16", name: "Martillo 16 oz", unit: "und", stock: "4.000", min_stock: "5.000", average_cost: "19000.0000", value: "76000.00", below_min: true, negative: false },
    { product: 5, sku: "PIN-VIN-B", name: "Pintura vinilo blanca", unit: "gal", stock: "-2.000", min_stock: "0.000", average_cost: null, value: "0.00", below_min: false, negative: true },
  ],
};

export const margins: MarginsReport = {
  from: "2026-10-16", to: "2026-10-16",
  totals: { net_sales: "1008487.39", cost: "822150.00", margin: "186337.39", margin_pct: "18.5", cost_estimated: true, services_net_sales: "20168.07" },
  rows: [
    { product: 2, sku: "MAR-16", name: "Martillo 16 oz", is_service: false, net_sales: "188235.28", cost: "152000.00", margin: "36235.28", margin_pct: "19.2", cost_estimated: true },
    { product: 9, sku: "LAV-150", name: "Lavado moto hasta 150 cc", is_service: true, net_sales: "20168.07", cost: "0.00", margin: "20168.07", margin_pct: "100.0", cost_estimated: false },
  ],
};


export const quotes: QuotesReport = {
  from: "2026-10-16", to: "2026-10-22",
  totals: {
    quotes: 5, quoted: "576000.00", converted: "84000.00", rate: "14.6", with_sales: 2,
    by_status: { VALID: 2, CONVERTED: 1, VOIDED: 0, EXPIRED: 2 }, // todas distintas: un estado no se confunde con otro
  },
  by_salesperson: [
    { salesperson: "camilo", quotes: 1, with_sales: 0, quoted: "320000.00", converted: "0.00", rate: "0.0" },
    { salesperson: "andres", quotes: 4, with_sales: 2, quoted: "256000.00", converted: "84000.00", rate: "32.8" },
  ],
  rows: [
    { id: 5, number: "COT-000005", created_at: "2026-10-22T20:00:00Z", customer: "Constructora Los Pinos", created_by: "camilo", status: "VALID", status_label: "Vigente", total: "320000.00", converted: "0.00" },
    { id: 1, number: "COT-000001", created_at: "2026-10-22T14:30:00Z", customer: "Don Jorge", created_by: "andres", status: "CONVERTED", status_label: "Convertida", total: "56000.00", converted: "56000.00" },
  ],
  truncated: false,
};
