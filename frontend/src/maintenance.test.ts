import { describe, expect, it } from "vitest";

import {
  daysUntil, dueLabel, emptyPlan, planForm, planInterval, planPayload, planProblem, reminderTarget, whatsappLink, whatsappMessage,
  whatsappNumber,
} from "./maintenance";

const row = {
  owner: { name: "Jorge Ramírez" },
  motorcycle: { plate: "XYZ12A", vin: "", brand: "Bajaj", model: "Boxer CT 100" },
  plan: { name: "Cambio de aceite" },
  due_on: "2026-12-15",
  by_km: false,
};

describe("WhatsApp", () => {
  it("un celular de Colombia lleva el 57 delante", () => {
    expect(whatsappNumber("300 123 4567")).toBe("573001234567");
    expect(whatsappNumber("+57 310-999-8877")).toBe("573109998877");
    expect(whatsappNumber("573001234567")).toBe("573001234567");
  });

  it("un fijo u otro número no tiene WhatsApp", () => {
    for (const phone of ["608 435 1234", "4351234", "", "300 123 456", "3001234567 8"]) expect(whatsappNumber(phone)).toBeNull();
  });

  it("el mensaje dice quién escribe, la moto, el plan y desde cuándo", () => {
    expect(whatsappMessage(row, "Moto Repuestos Arias")).toBe(
      "Hola, Jorge Ramírez. Le escribimos de Moto Repuestos Arias. "
      + "A su moto XYZ12A · Bajaj Boxer CT 100 le toca cambio de aceite desde el 15 de diciembre. ¿Cuándo la puede traer?");
    expect(whatsappMessage({ ...row, by_km: true }, "Arias")).toContain("le toca cambio de aceite por kilometraje.");
    expect(whatsappMessage({ ...row, due_on: null }, "Arias")).toContain("le toca cambio de aceite.");
  });

  it("el enlace abre WhatsApp con el número y el mensaje", () => {
    expect(whatsappLink("300 123 4567", "Hola, ¿cómo va?")).toBe("https://wa.me/573001234567?text=Hola%2C%20%C2%BFc%C3%B3mo%20va%3F");
    expect(whatsappLink("608 435 1234", "Hola")).toBeNull();
  });
});

describe("cuándo vence", () => {
  it("cuenta los días entre fechas", () => {
    expect(daysUntil("2026-11-02", "2026-10-30")).toBe(3);
    expect(daysUntil("2026-10-27", "2026-10-30")).toBe(-3);
    expect(daysUntil("2027-01-01", "2026-12-31")).toBe(1);
  });

  it("dice si venció, vence hoy o en cuántos días, y si es por km aprox.", () => {
    const today = "2026-10-30";
    const due = (due_on: string | null, by_km = false, estimated = false) => dueLabel({ due_on, by_km, estimated }, today);
    expect(due("2026-10-27")).toBe("Venció hace 3 días");
    expect(due("2026-10-29")).toBe("Venció hace 1 día");
    expect(due("2026-10-30")).toBe("Vence hoy");
    expect(due("2026-10-31")).toBe("Vence en 1 día");
    expect(due("2026-11-01", true, true)).toBe("Vence en 2 días por km (aprox.)");
    expect(due("2026-10-29", true)).toBe("Venció hace 1 día por km");
    expect(due(null)).toBe("Sin fecha: se sabrá cuando la moto vuelva");
  });
});

describe("para cuándo es", () => {
  it("la fecha, los km o los dos", () => {
    expect(reminderTarget({ due_date: "2027-01-28", due_mileage: 18420 })).toBe("el 28 de enero de 2027 o a los 18.420 km");
    expect(reminderTarget({ due_date: null, due_mileage: 30000 })).toBe("a los 30.000 km");
    expect(reminderTarget({ due_date: "2027-01-28", due_mileage: null })).toBe("el 28 de enero de 2027");
  });
});

describe("planes", () => {
  it("el intervalo en palabras", () => {
    expect(planInterval({ every_km: 3000, every_days: 90 })).toBe("Cada 3.000 km o 90 días");
    expect(planInterval({ every_km: 15000, every_days: null })).toBe("Cada 15.000 km");
    expect(planInterval({ every_km: null, every_days: 180 })).toBe("Cada 180 días");
  });

  const oil = { id: 21, sku: "ACE-20W50", name: "Aceite 20W50" };
  const form = { ...emptyPlan(), name: "Cambio de aceite", everyKm: "3000", products: [oil] };

  it("lo que falta para guardarlo", () => {
    expect(planProblem(emptyPlan())).toBe("Escribe el nombre del plan.");
    expect(planProblem({ ...form, everyKm: "" })).toBe("Di cada cuántos km, cada cuántos días o las dos cosas.");
    expect(planProblem({ ...form, everyKm: "0" })).toBe("Los km van en números mayores que cero.");
    expect(planProblem({ ...form, everyKm: "3.000" })).toBe("Los km van en números mayores que cero.");
    expect(planProblem({ ...form, everyDays: "0" })).toBe("Los días van en números mayores que cero.");
    expect(planProblem({ ...form, products: [] })).toBe("Elige al menos un producto o servicio que lo cumpla.");
    expect(planProblem(form)).toBeNull();
    expect(planProblem({ ...form, everyKm: "", everyDays: "90" })).toBeNull();
  });

  it("el cuerpo de la API y de vuelta al formulario", () => {
    expect(planPayload({ ...form, name: " Cambio de aceite ", everyDays: " " })).toEqual({
      name: "Cambio de aceite", every_km: 3000, every_days: null, products: [21], is_active: true,
    });
    expect(planForm({ id: 1, name: "Frenos", every_km: null, every_days: 180, products: [21], product_list: [oil], is_active: false }))
      .toEqual({ name: "Frenos", everyKm: "", everyDays: "180", products: [oil], isActive: false });
  });
});
