// Motos del taller (spec 009), sin React para poder probarlo. El servidor (workshop/rules.py) es
// la fuente de verdad: aquí solo se avisa antes de enviar.
import type { Motorcycle } from "./api";

/** Sugerencias para la marca (texto libre), las mismas del servidor. */
export const BRANDS = [
  "AKT", "Auteco", "Bajaj", "Hero", "Honda", "Kawasaki", "KTM", "Royal Enfield",
  "Suzuki", "TVS", "Victory", "Yamaha",
];

/** Mayúsculas, sin espacios, guiones ni puntos: `xyz-12a` y `XYZ 12A` son la misma placa. */
export function normalizeCode(value: string): string {
  return value.replace(/[\s.-]/g, "").toUpperCase();
}

export interface MotorcycleForm {
  plate: string;
  vin: string;
  brand: string;
  model: string;
  year: string;
  displacement_cc: string;
  color: string;
  notes: string;
}

export const emptyForm = (): MotorcycleForm => ({
  plate: "", vin: "", brand: "", model: "", year: "", displacement_cc: "", color: "", notes: "",
});

export const formOf = (m: Motorcycle): MotorcycleForm => ({
  plate: m.plate, vin: m.vin, brand: m.brand, model: m.model, year: m.year?.toString() ?? "",
  displacement_cc: m.displacement_cc?.toString() ?? "", color: m.color, notes: m.notes,
});

/** Lo primero que está mal en el formulario, o null si se puede enviar. */
export function formProblem(form: MotorcycleForm, today = new Date()): string | null {
  const plate = normalizeCode(form.plate), vin = normalizeCode(form.vin);
  if (!plate && !vin) return "Escribe la placa o, si no tiene, el número de chasis.";
  if (plate && !/^[A-Z0-9]{4,8}$/.test(plate)) return "La placa debe tener de 4 a 8 letras o números, p. ej. ABC12D.";
  if (vin && !/^[A-Z0-9]{6,20}$/.test(vin)) return "El chasis debe tener de 6 a 20 letras o números.";
  if (!form.brand.trim()) return "Escribe la marca.";
  const maxYear = today.getFullYear() + 1;
  if (form.year.trim() && !(/^\d+$/.test(form.year.trim()) && +form.year >= 1950 && +form.year <= maxYear)) {
    return `El año debe estar entre 1950 y ${maxYear}.`;
  }
  if (form.displacement_cc.trim() && !(/^\d+$/.test(form.displacement_cc.trim()) && +form.displacement_cc > 0)) {
    return "El cilindraje va en centímetros cúbicos, p. ej. 125.";
  }
  return null;
}

/** El cuerpo que espera la API: códigos limpios y números o null. */
export function payload(form: MotorcycleForm) {
  const number = (v: string) => (v.trim() ? Number(v) : null);
  return {
    plate: normalizeCode(form.plate), vin: normalizeCode(form.vin), brand: form.brand.trim(), model: form.model.trim(),
    year: number(form.year), displacement_cc: number(form.displacement_cc), color: form.color.trim(), notes: form.notes.trim(),
  };
}

/** "XYZ12A · Bajaj Boxer CT 100", o "Chasis 9FLP… · Honda" si no tiene placa. */
export function describeMotorcycle(m: Pick<Motorcycle, "plate" | "vin" | "brand" | "model">): string {
  const name = [m.brand, m.model].filter(Boolean).join(" ");
  return `${m.plate || `Chasis ${m.vin}`} · ${name}`;
}

export const formatKm = (km: number) => `${km.toLocaleString("es-CO")} km`;

/** Bajar el kilometraje exige una nota (cambio de tablero o error). */
export const mileageNeedsNote = (current: number, next: number) => next < current;
