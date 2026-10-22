// Período de los reportes (spec 004, decisión 2): hoy por defecto, accesos rápidos y rango libre.
// Las fechas viajan como texto AAAA-MM-DD; se calculan en UTC para no depender de la zona del equipo.

export interface Period {
  from: string;
  to: string;
}

export type Preset = "today" | "yesterday" | "week" | "month";

export const PRESETS: { id: Preset; label: string }[] = [
  { id: "today", label: "Hoy" },
  { id: "yesterday", label: "Ayer" },
  { id: "week", label: "Esta semana" },
  { id: "month", label: "Este mes" },
];

const DAY_MS = 86_400_000;

function parse(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d));
}

function format(date: Date): string {
  return date.toISOString().slice(0, 10);
}

/** Período de un acceso rápido. La semana empieza el lunes; semana y mes llegan hasta hoy. */
export function presetPeriod(preset: Preset, today: string): Period {
  const t = parse(today);
  switch (preset) {
    case "today":
      return { from: today, to: today };
    case "yesterday": {
      const y = format(new Date(t.getTime() - DAY_MS));
      return { from: y, to: y };
    }
    case "week": {
      const sinceMonday = (t.getUTCDay() + 6) % 7; // domingo = 6
      return { from: format(new Date(t.getTime() - sinceMonday * DAY_MS)), to: today };
    }
    case "month":
      return { from: format(new Date(Date.UTC(t.getUTCFullYear(), t.getUTCMonth(), 1))), to: today };
  }
}

/**
 * El acceso rápido que corresponde a un período, para resaltar su botón. Si el usuario pulsó uno
 * (`chosen`) y el período sigue siendo el suyo, gana ese: el lunes "Hoy" y "Esta semana" son el
 * mismo período, y el día 1 lo son "Hoy" y "Este mes".
 */
export function matchPreset(period: Period, today: string, chosen: Preset | null = null): Preset | null {
  if (chosen) {
    const p = presetPeriod(chosen, today);
    if (p.from === period.from && p.to === period.to) return chosen;
  }
  return PRESETS.find((p) => {
    const q = presetPeriod(p.id, today);
    return q.from === period.from && q.to === period.to;
  })?.id ?? null;
}

/** URL de un reporte. El inventario es una foto de hoy: no lleva período. */
/** Reportes que no se filtran por caja: el inventario es una foto y las cotizaciones no pasan por caja. */
export const NO_REGISTER = ["inventory", "quotes"];

export function reportUrl(name: string, period: Period, register = ""): string {
  const q = new URLSearchParams();
  if (name !== "inventory") {
    q.set("from", period.from);
    q.set("to", period.to);
  }
  if (register && !NO_REGISTER.includes(name)) q.set("register", register);
  const s = q.toString();
  return `/api/reports/${name}/${s ? `?${s}` : ""}`;
}

const dayFormat = new Intl.DateTimeFormat("es-CO", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" });

/** "2026-10-15" → "jue, 15 oct" (sin correrse de día por la zona horaria). */
export function formatDay(iso: string): string {
  return dayFormat.format(parse(iso));
}

/** "18.5" → "18,5 %"; sin base → "—". */
export function formatPct(value: string | null): string {
  return value == null ? "—" : `${value.replace(".", ",")} %`;
}
