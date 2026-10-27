import { describe, expect, it } from "vitest";

import {
  describeMotorcycle, emptyForm, formatKm, formOf, formProblem, mileageNeedsNote, normalizeCode, payload, type MotorcycleForm,
} from "./motorcycle";

const form = (over: Partial<MotorcycleForm> = {}): MotorcycleForm => ({ ...emptyForm(), plate: "xyz-12a", brand: "Bajaj", ...over });
const today = new Date(2026, 9, 27);

describe("placa y chasis", () => {
  it("se escriben como sea y se guardan limpios", () => {
    expect(normalizeCode(" x.y.z-12 a ")).toBe("XYZ12A");
    expect(payload(form({ vin: "9fl-pcj 2" })).vin).toBe("9FLPCJ2");
  });
});

describe("lo que se avisa antes de enviar", () => {
  it("placa o chasis, y marca", () => {
    expect(formProblem(form(), today)).toBeNull();
    expect(formProblem(form({ plate: " - " }), today)).toMatch(/placa o, si no tiene, el número de chasis/);
    expect(formProblem(form({ plate: "", vin: "9FLPCJ" }), today)).toBeNull();
    expect(formProblem(form({ brand: "  " }), today)).toBe("Escribe la marca.");
  });

  it("largos de placa (4 a 8) y chasis (6 a 20)", () => {
    expect(formProblem(form({ plate: "AB1" }), today)).toMatch(/La placa debe tener de 4 a 8/);
    expect(formProblem(form({ plate: "AB12" }), today)).toBeNull();
    expect(formProblem(form({ plate: "ABCD1234" }), today)).toBeNull();
    expect(formProblem(form({ plate: "ABCD12345" }), today)).toMatch(/La placa/);
    expect(formProblem(form({ plate: "ABC12$" }), today)).toMatch(/La placa/);
    expect(formProblem(form({ vin: "AB123" }), today)).toMatch(/El chasis debe tener de 6 a 20/);
    expect(formProblem(form({ vin: "A".repeat(20) }), today)).toBeNull();
    expect(formProblem(form({ vin: "A".repeat(21) }), today)).toMatch(/El chasis/);
  });

  it("año de 1950 al próximo y cilindraje positivo", () => {
    expect(formProblem(form({ year: "1950" }), today)).toBeNull();
    expect(formProblem(form({ year: "2027" }), today)).toBeNull();
    for (const year of ["1949", "2028", "20a5", "99"]) {
      expect(formProblem(form({ year }), today)).toBe("El año debe estar entre 1950 y 2027.");
    }
    expect(formProblem(form({ displacement_cc: "125" }), today)).toBeNull();
    for (const cc of ["0", "12.5", "abc"]) expect(formProblem(form({ displacement_cc: cc }), today)).toMatch(/cilindraje/);
  });
});

describe("lo que se envía", () => {
  it("números o null y textos recortados", () => {
    expect(payload(form({ year: " 2019 ", displacement_cc: "", brand: " Bajaj ", model: " Boxer ", color: " Negro ", notes: "  " }))).toEqual({
      plate: "XYZ12A", vin: "", brand: "Bajaj", model: "Boxer", year: 2019, displacement_cc: null, color: "Negro", notes: "",
    });
  });

  it("el formulario de una moto guardada se puede volver a enviar igual", () => {
    const saved = { plate: "XYZ12A", vin: "", brand: "Bajaj", model: "Boxer", year: null, displacement_cc: 100, color: "", notes: "" };
    expect(payload(formOf({ ...saved, id: 1, is_active: true } as never))).toEqual(saved);
  });
});

describe("cómo se muestra", () => {
  it("placa o chasis, marca y modelo", () => {
    expect(describeMotorcycle({ plate: "XYZ12A", vin: "", brand: "Bajaj", model: "Boxer" })).toBe("XYZ12A · Bajaj Boxer");
    expect(describeMotorcycle({ plate: "", vin: "9FLPCJ", brand: "Honda", model: "" })).toBe("Chasis 9FLPCJ · Honda");
    expect(formatKm(15200)).toBe("15.200 km");
  });

  it("solo bajar el kilometraje pide nota", () => {
    expect(mileageNeedsNote(1000, 999)).toBe(true);
    expect(mileageNeedsNote(1000, 1000)).toBe(false);
    expect(mileageNeedsNote(1000, 1500)).toBe(false);
  });
});
