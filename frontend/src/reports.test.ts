import { describe, expect, it } from "vitest";

import { formatDay, formatPct, matchPreset, presetPeriod, reportUrl } from "./reports";

describe("presetPeriod", () => {
  const friday = "2026-10-16";

  it("hoy y ayer son un solo día", () => {
    expect(presetPeriod("today", friday)).toEqual({ from: friday, to: friday });
    expect(presetPeriod("yesterday", friday)).toEqual({ from: "2026-10-15", to: "2026-10-15" });
    expect(presetPeriod("yesterday", "2026-01-01")).toEqual({ from: "2025-12-31", to: "2025-12-31" });
  });

  it("la semana empieza el lunes y llega hasta hoy", () => {
    expect(presetPeriod("week", friday)).toEqual({ from: "2026-10-12", to: friday });
    expect(presetPeriod("week", "2026-10-12")).toEqual({ from: "2026-10-12", to: "2026-10-12" });
    expect(presetPeriod("week", "2026-10-18")).toEqual({ from: "2026-10-12", to: "2026-10-18" }); // domingo
    expect(presetPeriod("week", "2026-11-01")).toEqual({ from: "2026-10-26", to: "2026-11-01" }); // cruza el mes
  });

  it("el mes va del 1 a hoy", () => {
    expect(presetPeriod("month", friday)).toEqual({ from: "2026-10-01", to: friday });
    expect(presetPeriod("month", "2026-10-01")).toEqual({ from: "2026-10-01", to: "2026-10-01" });
  });
});

describe("matchPreset", () => {
  it("reconoce el acceso rápido de un período, o ninguno", () => {
    expect(matchPreset({ from: "2026-10-16", to: "2026-10-16" }, "2026-10-16")).toBe("today");
    expect(matchPreset({ from: "2026-10-12", to: "2026-10-16" }, "2026-10-16")).toBe("week");
    expect(matchPreset({ from: "2026-10-02", to: "2026-10-16" }, "2026-10-16")).toBeNull();
    expect(matchPreset({ from: "2026-10-12", to: "2026-10-14" }, "2026-10-16")).toBeNull(); // lunes a miércoles
  });

  it("el lunes, hoy y esta semana coinciden: gana hoy", () => {
    expect(matchPreset({ from: "2026-10-12", to: "2026-10-12" }, "2026-10-12")).toBe("today");
  });
});

describe("reportUrl", () => {
  const period = { from: "2026-10-01", to: "2026-10-16" };

  it("lleva el período y la caja", () => {
    expect(reportUrl("sales", period)).toBe("/api/reports/sales/?from=2026-10-01&to=2026-10-16");
    expect(reportUrl("shifts", period, "2")).toBe("/api/reports/shifts/?from=2026-10-01&to=2026-10-16&register=2");
  });

  it("el inventario es una foto de hoy: sin período ni caja", () => {
    expect(reportUrl("inventory", period, "2")).toBe("/api/reports/inventory/");
  });
});

describe("formatos", () => {
  it("el día no se corre por la zona horaria", () => {
    expect(formatDay("2026-10-15")).toMatch(/jue.*15.*oct/);
    expect(formatDay("2026-10-01")).toMatch(/\b1\b.*oct/);
  });

  it("porcentaje con coma decimal; sin base, raya", () => {
    expect(formatPct("18.5")).toBe("18,5 %");
    expect(formatPct("-3.0")).toBe("-3,0 %");
    expect(formatPct(null)).toBe("—");
  });
});
