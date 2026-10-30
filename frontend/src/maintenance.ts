// Mantenimientos (spec 012), sin React para poder probarlo. El servidor (workshop/maintenance.py)
// decide qué vence; aquí se arma el aviso por WhatsApp y se dice cuándo vence.
import type { MaintenancePlan, Reminder, ReminderStatus } from "./api";
import { describeMotorcycle } from "./motorcycle";

export const REMINDER_LABELS: Record<ReminderStatus, string> = {
  PENDING: "Pendiente",
  NOTIFIED: "Avisado",
  DONE: "Hecho",
  DISMISSED: "Descartado",
};

/**
 * El número para wa.me: un celular de Colombia (10 dígitos que empiezan por 3) con el 57 delante.
 * Un fijo u otro número no sirve: no se ofrece el botón (regla 8).
 */
export function whatsappNumber(phone: string): string | null {
  let digits = phone.replace(/\D/g, "");
  if (digits.length === 12 && digits.startsWith("57")) digits = digits.slice(2);
  return /^3\d{9}$/.test(digits) ? `57${digits}` : null;
}

const longDate = (iso: string) =>
  new Date(`${iso}T12:00:00`).toLocaleDateString("es-CO", { day: "numeric", month: "long" });

/** El mensaje que recepción manda desde su WhatsApp. */
export function whatsappMessage(row: {
  owner: { name: string };
  motorcycle: { plate: string; vin: string; brand: string; model: string };
  plan: { name: string };
  due_on: string | null;
  by_km: boolean;
}, business: string): string {
  const when = row.by_km ? "por kilometraje" : row.due_on ? `desde el ${longDate(row.due_on)}` : "";
  return [
    `Hola, ${row.owner.name}. Le escribimos de ${business}.`,
    `A su moto ${describeMotorcycle(row.motorcycle)} le toca ${row.plan.name.toLowerCase()}${when ? ` ${when}` : ""}.`,
    "¿Cuándo la puede traer?",
  ].join(" ");
}

/** El enlace que abre WhatsApp con el número y el mensaje, o null si el teléfono no es un celular. */
export function whatsappLink(phone: string, message: string): string | null {
  const number = whatsappNumber(phone);
  return number ? `https://wa.me/${number}?text=${encodeURIComponent(message)}` : null;
}

const DAY_MS = 86_400_000;
/** Días de `today` a `iso` (ambas fechas sin hora). */
export const daysUntil = (iso: string, today: string) =>
  Math.round((Date.parse(`${iso}T00:00:00Z`) - Date.parse(`${today}T00:00:00Z`)) / DAY_MS);

/** "Venció hace 3 días", "Vence hoy", "Vence en 2 días", con "por km aprox." si va por el uso estimado. */
export function dueLabel(reminder: Pick<Reminder, "due_on" | "by_km" | "estimated">, today: string): string {
  if (!reminder.due_on) return "Sin fecha: se sabrá cuando la moto vuelva";
  const days = daysUntil(reminder.due_on, today);
  const when = days < 0 ? `Venció hace ${-days} ${-days === 1 ? "día" : "días"}`
    : days === 0 ? "Vence hoy"
    : `Vence en ${days} ${days === 1 ? "día" : "días"}`;
  return reminder.by_km ? `${when} por km${reminder.estimated ? " (aprox.)" : ""}` : when;
}

/** "Cada 3.000 km o 90 días", "Cada 15.000 km", "Cada 180 días". */
export function planInterval(plan: Pick<MaintenancePlan, "every_km" | "every_days">): string {
  const parts = [
    plan.every_km ? `${plan.every_km.toLocaleString("es-CO")} km` : null,
    plan.every_days ? `${plan.every_days} días` : null,
  ].filter(Boolean);
  return `Cada ${parts.join(" o ")}`;
}

export interface PlanForm {
  name: string;
  everyKm: string;
  everyDays: string;
  products: { id: number; sku: string; name: string }[];
  isActive: boolean;
}

export const emptyPlan = (): PlanForm => ({ name: "", everyKm: "", everyDays: "", products: [], isActive: true });

export const planForm = (plan: MaintenancePlan): PlanForm => ({
  name: plan.name,
  everyKm: plan.every_km?.toString() ?? "",
  everyDays: plan.every_days?.toString() ?? "",
  products: plan.product_list,
  isActive: plan.is_active,
});

const positive = (value: string) => /^\d+$/.test(value.trim()) && Number(value) > 0;

/** Lo primero que falta para guardar el plan, o null. */
export function planProblem(form: PlanForm): string | null {
  if (!form.name.trim()) return "Escribe el nombre del plan.";
  if (!form.everyKm.trim() && !form.everyDays.trim()) return "Di cada cuántos km, cada cuántos días o las dos cosas.";
  if (form.everyKm.trim() && !positive(form.everyKm)) return "Los km van en números mayores que cero.";
  if (form.everyDays.trim() && !positive(form.everyDays)) return "Los días van en números mayores que cero.";
  if (!form.products.length) return "Elige al menos un producto o servicio que lo cumpla.";
  return null;
}

/** El cuerpo que espera la API. */
export function planPayload(form: PlanForm) {
  const number = (v: string) => (v.trim() ? Number(v) : null);
  return {
    name: form.name.trim(), every_km: number(form.everyKm), every_days: number(form.everyDays),
    products: form.products.map((p) => p.id), is_active: form.isActive,
  };
}

const fullDate = (iso: string) =>
  new Date(`${iso}T12:00:00`).toLocaleDateString("es-CO", { day: "numeric", month: "long", year: "numeric" });

/** Para cuándo es: "el 28 de enero de 2027 o a los 18.420 km". */
export function reminderTarget(reminder: Pick<Reminder, "due_date" | "due_mileage">): string {
  return [
    reminder.due_date ? `el ${fullDate(reminder.due_date)}` : null,
    reminder.due_mileage != null ? `a los ${reminder.due_mileage.toLocaleString("es-CO")} km` : null,
  ].filter(Boolean).join(" o ");
}
