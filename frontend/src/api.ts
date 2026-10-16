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
