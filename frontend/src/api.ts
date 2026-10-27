// Cliente de la API. La sesión viaja en una cookie HttpOnly (same-origin); las escrituras
// llevan el token CSRF que Django deja en la cookie "csrftoken".

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

function csrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : "";
}

/** Convierte las respuestas de error de DRF (detail, lista o campos) en un mensaje legible. */
export function errorMessage(body: unknown): string {
  if (body == null) return "Error inesperado.";
  if (typeof body === "string") return body;
  if (Array.isArray(body)) return body.map(errorMessage).join(" ");
  if (typeof body === "object") {
    const obj = body as Record<string, unknown>;
    if ("detail" in obj) return errorMessage(obj.detail);
    return Object.entries(obj)
      .map(([field, value]) =>
        field === "non_field_errors" ? errorMessage(value) : `${field}: ${errorMessage(value)}`,
      )
      .join(" ");
  }
  return String(body);
}

/** Una red lenta no debe dejar la caja colgada: pasado este tiempo se trata como "sin conexión". */
export const TIMEOUT_MS = 10_000;

export async function api<T>(path: string, options: { method?: string; body?: unknown } = {}): Promise<T> {
  const method = options.method ?? "GET";
  const headers: Record<string, string> = { Accept: "application/json" };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET") headers["X-CSRFToken"] = csrfToken();

  const res = await fetch(path, {
    method,
    headers,
    credentials: "same-origin",
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    signal: AbortSignal.timeout(TIMEOUT_MS),
  });
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const message = data == null ? `El servidor respondió ${res.status} ${res.statusText}.` : errorMessage(data);
    throw new ApiError(res.status, message);
  }
  return data as T;
}

// --- Tipos de la API ----------------------------------------------------------

export interface Me {
  id: number;
  username: string;
  first_name: string;
  last_name: string;
  roles: string[];
  permissions: string[];
  /** Contraseña temporal puesta por un administrador: hay que cambiarla antes de usar la app. */
  must_change_password: boolean;
  /** Módulo de taller activo en esta instalación (spec 009). Falta en una sesión guardada de antes: apagado. */
  workshop_enabled?: boolean;
}

export interface ProductUnit {
  unit: string;
  factor: string;
  barcode: string | null;
}

export interface Product {
  id: number;
  sku: string;
  name: string;
  category: string;
  base_unit: string;
  barcode: string | null;
  sale_price: string;
  tax_rate: string;
  /** Excluido de IVA (no causa IVA), distinto de exento al 0 %. Opcional: el catálogo guardado sin conexión puede ser anterior. */
  vat_excluded?: boolean;
  allows_fractions: boolean;
  min_stock: string;
  units: ProductUnit[];
}

export interface Register {
  id: number;
  code: string;
  name: string;
  warehouse: string;
  open_shift: number | null;
}

export type PaymentMethod = "CASH" | "CARD" | "TRANSFER";

export interface Shift {
  id: number;
  register: string;
  status: "OPEN" | "CLOSED";
  opening_float: string;
  expected_cash: string | null;
  counted_cash: string | null;
  difference: string | null;
  summary: {
    sales: number;
    by_method: Record<PaymentMethod, string>;
    refunds: Record<PaymentMethod, string>;
    expected_cash: string;
  };
}

export interface Sale {
  id: number;
  number: string;
  total: string;
  subtotal: string;
  tax: string;
  payments: { method: PaymentMethod; amount: string; received: string; change: string }[];
}

export interface Warehouse {
  id: number;
  code: string;
  name: string;
  /** La bodega principal (spec 008): la API la trae primero. */
  is_default: boolean;
}

export interface StockLevel {
  product: string;
  warehouse: string;
  quantity: string;
  below_min: boolean;
}

export interface StockMovement {
  id: string;
  quantity: string;
  balance_after: string;
}

export interface OrderLine {
  id: number;
  product: number;
  sku: string;
  name: string;
  unit: string;
  quantity: string;
  unit_price: string;
  total: string;
}

export interface StockWarning {
  sku: string;
  name: string;
  kind: "sin_existencias" | "bajo_minimo";
  available: string;
}

export interface Order {
  id: number;
  code: number;
  business_date: string;
  status: "PENDING" | "PAID" | "CANCELLED" | "EXPIRED";
  salesperson: string;
  total: string;
  created_at: string;
  sale_number: string | null;
  lines: OrderLine[];
  warnings?: StockWarning[];
}

// --- Supervisor (spec 003) ------------------------------------------------------

export interface SaleListItem {
  id: number;
  number: string;
  occurred_at: string;
  register: string;
  seller: string;
  salesperson: string;
  order_code: number | null;
  total: string;
  status: "COMPLETED" | "VOIDED";
  offline: boolean;
  needs_review: boolean;
}

export interface SaleDetailLine {
  id: number;
  product: string; // SKU
  name: string;
  unit: string;
  quantity: string;
  returned_quantity: string;
  unit_price: string;
  catalog_price: string;
  total: string;
}

export interface SaleReturn {
  id: number;
  number: string;
  reason: string;
  total: string;
  refund_method: PaymentMethod;
  user: string;
  created_at: string;
}

export interface SaleDetail extends Omit<SaleListItem, "register"> {
  register: string;
  shift_open: boolean;
  subtotal: string;
  tax: string;
  void_reason: string;
  voided_at: string | null;
  reviewed_at: string | null;
  review_note: string;
  lines: SaleDetailLine[];
  payments: { method: PaymentMethod; amount: string; received: string; change: string; reference: string }[];
  returns: SaleReturn[];
}

export interface AppUser {
  id: number;
  username: string;
  first_name: string;
  last_name: string;
  email: string;
  is_active: boolean;
  roles: string[];
  must_change_password: boolean;
  last_login: string | null;
}

export interface Role {
  id: number;
  name: string;
  permissions: string[];
}

export interface PermissionInfo {
  code: string;
  description: string;
}

// --- Reportes (spec 004). El dinero llega como texto con 2 decimales y las cantidades con 3. ---

export interface ReportRow {
  sales_count: number;
  total: string;
  returns: string;
  net: string;
}

export interface SalesReport {
  from: string;
  to: string;
  totals: {
    sales_count: number;
    total: string;
    subtotal: string;
    tax: string;
    returns_total: string;
    returns_subtotal: string;
    returns_tax: string;
    net_total: string;
    net_subtotal: string;
    net_tax: string;
    average_ticket: string;
  };
  by_day: (ReportRow & { day: string })[];
  by_register: (ReportRow & { register: string })[];
  by_salesperson: (ReportRow & { salesperson: string })[];
  by_method: { method: PaymentMethod; label: string; payments: string; refunds: string; net: string }[];
}

export interface ProductReportRow {
  product: number;
  sku: string;
  name: string;
  unit: string;
  sales_count: number;
  quantity: string;
  total: string;
  subtotal: string;
}

export interface ProductsReport {
  from: string;
  to: string;
  by_quantity: ProductReportRow[];
  by_value: ProductReportRow[];
  not_moved: { product: number; sku: string; name: string; unit: string; stock: string }[];
}

export interface InventoryReport {
  totals: { value: string; products: number; below_min: number; negative: number };
  rows: {
    product: number;
    sku: string;
    name: string;
    unit: string;
    stock: string;
    min_stock: string;
    /** null si no hay existencias positivas. */
    average_cost: string | null;
    value: string;
    below_min: boolean;
    negative: boolean;
  }[];
}

export interface MarginRow {
  net_sales: string;
  cost: string;
  margin: string;
  /** Porcentaje con un decimal; null si la venta neta es 0. */
  margin_pct: string | null;
  cost_estimated: boolean;
}

export interface MarginsReport {
  from: string;
  to: string;
  totals: MarginRow;
  rows: (MarginRow & { product: number; sku: string; name: string })[];
}

export interface ShiftsReport {
  from: string;
  to: string;
  totals: {
    shifts: number;
    expected_cash: string;
    counted_cash: string;
    difference: string;
    shortage: string;
    overage: string;
    by_method: Record<PaymentMethod, string>;
  };
  rows: {
    shift: number;
    register: string;
    opened_by: string;
    opened_at: string;
    closed_by: string | null;
    closed_at: string;
    sales_count: number;
    opening_float: string;
    by_method: Record<PaymentMethod, string>;
    expected_cash: string;
    counted_cash: string;
    difference: string;
    notes: string;
  }[];
}

// --- Documentos electrónicos DIAN (spec 005) ---

export type FiscalStatus = "PENDING" | "VALIDATED" | "REJECTED";

export interface FiscalDocumentRow {
  id: number;
  kind: "POS" | "INVOICE" | "POS_ADJUSTMENT" | "CREDIT_NOTE";
  kind_label: string;
  code: string;
  status: FiscalStatus;
  status_label: string;
  sale: number;
  sale_number: string;
  register: string;
  customer: string;
  customer_id: number;
  total: string;
  issued_at: string;
  attempts: number;
  last_error: string;
  next_attempt_at: string | null;
  validated_at: string | null;
  cude: string;
  /** Plazo de 48 horas para transmitir (art. 37). */
  deadline: string;
  alert: "overdue" | "due_soon" | null;
  /** Código del documento que esta nota espera que se valide primero. */
  waiting_for: string | null;
}

export interface FiscalDocumentDetail extends FiscalDocumentRow {
  subtotal: string;
  tax: string;
  qr_data: string;
  corrects: string | null;
  events: { at: string; kind: string; detail: string }[];
}

export interface FiscalInbox {
  summary: { pending: number; rejected: number; overdue: number; due_soon: number };
  results: FiscalDocumentRow[];
}

export interface Customer {
  id: number;
  id_type: string;
  id_type_label: string;
  id_number: string;
  check_digit: string;
  person_type: "1" | "2";
  name: string;
  email: string;
  phone: string;
  address: string;
  city: string;
  tax_responsibilities: string[];
  is_final_consumer: boolean;
}

/** Dueño de una moto (spec 009): el mismo cliente de la caja. */
export interface Owner {
  id: number;
  name: string;
  id_type: string;
  id_number: string;
  check_digit: string;
  phone: string;
}

export interface Motorcycle {
  id: number;
  /** Sin espacios ni guiones, en mayúsculas; vacía si la moto aún no tiene placa. */
  plate: string;
  /** Número de chasis: obligatorio si no hay placa. */
  vin: string;
  brand: string;
  model: string;
  year: number | null;
  displacement_cc: number | null;
  color: string;
  notes: string;
  is_active: boolean;
  mileage: number;
  mileage_at: string | null;
  owner: Owner;
  created_at: string;
  updated_at: string;
}

export interface MotorcycleDetail extends Motorcycle {
  /** El más reciente primero; el que no tiene `ended_at` es el dueño actual. */
  ownerships: { customer: Owner; started_at: string; ended_at: string | null }[];
  /** Las últimas 20 lecturas, la más reciente primero. */
  mileage_readings: { mileage: number; previous: number | null; note: string; recorded_at: string; recorded_by: string }[];
}

export interface Business {
  name: string;
  trade_name: string;
  nit: string;
  address: string;
  city: string;
  phone: string;
  email: string;
  tax_regime: string;
}

/** Representación gráfica para el tiquete de 80 mm (art. 19). La arma el servidor o, sin conexión, el POS. */
export interface TicketData {
  business: Business | null;
  title: string;
  code: string | null;
  status: FiscalStatus | null;
  /** Documento electrónico de la venta, para pedir que se envíe ya. */
  document_id?: number | null;
  sale_number: string | null;
  issued_at: string;
  register: string;
  cashier: string;
  customer: { name: string; document: string } | null;
  lines: { name: string; quantity: string; unit: string; unit_price: string; total: string }[];
  subtotal: string;
  tax: string;
  total: string;
  taxes: { rate: string; base: string; tax: string }[];
  payments: { label: string; amount: string }[];
  change: string;
  cude: string | null;
  qr_svg: string | null;
  resolution: string | null;
  notes: string[];
}

// --- Administración del catálogo (spec 006) ---

export interface Category {
  id: number;
  name: string;
  products: number;
}

export interface UnitOption {
  id: number;
  code: string;
  name: string;
}

export interface Presentation {
  id: number;
  unit: string;
  factor: string;
  barcode: string | null;
  is_active: boolean;
  /** Ya se usó en ventas o pedidos: su factor no cambia y no se puede borrar. */
  in_use: boolean;
}

export interface AdminProduct {
  id: number;
  sku: string;
  name: string;
  category: number;
  category_name: string;
  base_unit: string;
  barcode: string | null;
  sale_price: string;
  tax_rate: "0" | "5" | "19";
  vat_excluded: boolean;
  allows_fractions: boolean;
  min_stock: string;
  is_active: boolean;
  /** Lo creó alguien sin permiso de precios: inactivo hasta que le pongan precio. */
  price_pending: boolean;
  /** Tiene kardex: el SKU y la unidad base ya no cambian. */
  has_movements: boolean;
  units: Presentation[];
}

export interface PriceChange {
  old_price: string | null;
  new_price: string;
  user: string;
  at: string;
}

// --- Ajustes de inventario (spec 006) ---

export type AdjustmentReason = "DAMAGE" | "LOSS" | "INTERNAL_USE" | "EXPIRED" | "RECORD_ERROR" | "SURPLUS" | "PHYSICAL_COUNT";
export type AdjustmentStatus = "PENDING" | "APPROVED" | "REJECTED";

export interface AdjustmentLine {
  id: number;
  product: number;
  sku: string;
  name: string;
  unit: string;
  quantity: string;
  /** En unidad base, con signo: negativa sale. */
  base_quantity: string;
  base_unit: string;
  /** Valor al costo; null si el usuario no tiene reports.costs. */
  value: string | null;
}

export interface Adjustment {
  id: number;
  number: string;
  client_uuid: string;
  warehouse: string;
  reason: AdjustmentReason;
  reason_label: string;
  note: string;
  status: AdjustmentStatus;
  status_label: string;
  requested_by: string;
  created_at: string;
  decided_by: string | null;
  decided_at: string | null;
  rejection_note: string;
  lines: AdjustmentLine[];
}

// --- Conteos físicos (spec 006) ---

export type CountStatus = "OPEN" | "SUBMITTED" | "APPROVED" | "VOIDED";

export interface CountLine {
  id: number;
  product: number;
  sku: string;
  name: string;
  barcode: string | null;
  base_unit: string;
  units: { unit: string; factor: string; barcode: string | null }[];
  /** En unidad base; null si no se ha contado. */
  counted: string | null;
  counted_at: string | null;
  counted_by: string | null;
  marked_zero: boolean;
  /** Solo para quien aprueba (inventory.adjust); null en el conteo ciego. */
  expected: string | null;
  difference: string | null;
  /** Solo con reports.costs. */
  value: string | null;
}

export interface PhysicalCount {
  id: number;
  number: string;
  warehouse: string;
  category: string | null;
  status: CountStatus;
  status_label: string;
  opened_by: string;
  created_at: string;
  submitted_at: string | null;
  decided_by: string | null;
  decided_at: string | null;
  void_note: string;
  adjustment: string | null;
  total: number;
  counted: number;
  lines?: CountLine[];
}

// --- Traslados entre bodegas (spec 006) ---

export interface TransferLine {
  id: number;
  product: number;
  sku: string;
  name: string;
  unit: string;
  quantity: string;
  /** En unidad base, positiva. */
  base_quantity: string;
  base_unit: string;
  /** Valor movido al costo; null si el usuario no tiene reports.costs. */
  value: string | null;
}

export interface Transfer {
  id: number;
  number: string;
  client_uuid: string;
  origin: string;
  destination: string;
  note: string;
  created_by: string;
  created_at: string;
  lines: TransferLine[];
}

// --- Cotizaciones (spec 007) ---

export type QuoteStatus = "VALID" | "EXPIRED" | "CONVERTED" | "VOIDED";

export interface QuoteRow {
  id: number;
  number: string;
  customer: string;
  customer_phone: string;
  status: QuoteStatus;
  status_label: string;
  valid_until: string;
  total: string;
  created_by: string;
  created_at: string;
  lines_count: number;
}

export interface QuoteLine {
  id: number;
  product: number;
  sku: string;
  name: string;
  unit: string;
  quantity: string;
  unit_price: string;
  tax_rate: string;
  vat_excluded: boolean;
  total: string;
  subtotal: string;
  tax: string;
  /** El producto sigue a la venta (si no, esa línea ya no se convierte). */
  active: boolean;
  /** En pedidos pendientes de hoy, cobrado y lo que falta por convertir (3 decimales). */
  in_orders: string;
  charged: string;
  remaining: string;
}

export interface QuoteDetail extends QuoteRow {
  customer_id: number | null;
  customer_document: string | null;
  note: string;
  void_note: string;
  voided_by: string | null;
  duplicated_from: string | null;
  lines: QuoteLine[];
  subtotal: string;
  tax: string;
  taxes: { rate: string; base: string; tax: string }[];
  orders: { id: number; code: number; status: Order["status"]; total: string; sale_number: string | null; created_at: string }[];
  can_convert: boolean;
  business: Business;
  /** Solo al duplicar: SKU que quedaron por fuera porque ya no están a la venta. */
  skipped?: string[];
}

/** Reporte de cotizaciones (spec 007, T6): las creadas en el período y cuánto se convirtió en venta. */
export interface QuotesReport {
  from: string;
  to: string;
  totals: {
    quotes: number;
    quoted: string;
    converted: string;
    /** Porcentaje del valor cotizado que ya se cobró, con un decimal ("14.6"). */
    rate: string;
    with_sales: number;
    by_status: Record<QuoteStatus, number>;
  };
  by_salesperson: { salesperson: string; quotes: number; with_sales: number; quoted: string; converted: string; rate: string }[];
  rows: { id: number; number: string; created_at: string; customer: string; created_by: string; status: QuoteStatus; status_label: string; total: string; converted: string }[];
  /** Hay más de las que trae el detalle (los totales sí las cuentan todas). */
  truncated: boolean;
}
