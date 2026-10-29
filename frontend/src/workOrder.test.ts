import { describe, expect, it } from "vitest";

import type { WorkOrderDetail, WorkOrderLine, WorkOrderStatus } from "./api";
import {
  STATUS_FILTERS, emptyReceive, isEditable, isOpen, lineState, receivePayload, receiveProblem, receptionActions, unpricedLabor,
} from "./workOrder";

const line = (over: Partial<WorkOrderLine> = {}): WorkOrderLine => ({
  id: 1, product: 1, sku: "ACE-20W50", name: "Aceite 20W50", is_service: false, quantity: "1.000", unit_price: "32000.00",
  total: "32000.00", approved: true, taken: false, returned: false, added_by: "carlos", created_at: "2026-10-28T15:00:00Z", ...over,
});
const order = (status: WorkOrderStatus, over: Partial<WorkOrderDetail> = {}) => ({
  status, lines: [line()], till_order: null, sale: null, ...over,
}) as WorkOrderDetail;
const sale = { id: 1, number: "POS-1", total: "32000.00" };

describe("estados", () => {
  it("abiertas son las que no están entregadas ni canceladas; se editan hasta que está lista", () => {
    expect((["RECEIVED", "AWAITING_APPROVAL", "IN_REPAIR", "READY"] as const).every(isOpen)).toBe(true);
    expect(isOpen("DELIVERED") || isOpen("CANCELLED")).toBe(false);
    expect((["RECEIVED", "AWAITING_APPROVAL", "IN_REPAIR"] as const).every(isEditable)).toBe(true);
    expect(isEditable("READY") || isEditable("DELIVERED") || isEditable("CANCELLED")).toBe(false);
  });

  it("los filtros empiezan por las abiertas y terminan en todas", () => {
    expect(STATUS_FILTERS[0]).toEqual(["", "Abiertas"]);
    expect(STATUS_FILTERS.at(-1)).toEqual(["ALL", "Todas"]);
    expect(STATUS_FILTERS).toContainEqual(["AWAITING_APPROVAL", "Esperando aprobación"]);
    expect(STATUS_FILTERS).toHaveLength(8);
  });
});

describe("lo que puede hacer recepción", () => {
  it("con la orden en reparación: asignar, editar y cancelar; aprobar solo si hay algo por aprobar", () => {
    expect(receptionActions(order("IN_REPAIR"))).toEqual({
      assign: true, editLines: true, approve: false, sendToTill: false, deliver: false, cancel: true,
    });
    expect(receptionActions(order("IN_REPAIR", { lines: [line(), line({ id: 2, approved: false })] })).approve).toBe(true);
  });

  it("lista: a la caja una vez; se entrega y deja de cancelarse cuando está cobrada", () => {
    expect(receptionActions(order("READY"))).toEqual({
      assign: true, editLines: false, approve: false, sendToTill: true, deliver: false, cancel: true,
    });
    expect(receptionActions(order("READY", { till_order: { id: 1, code: "1234", total: "1" } })).sendToTill).toBe(false);
    expect(receptionActions(order("READY", { sale }))).toEqual({
      assign: true, editLines: false, approve: false, sendToTill: false, deliver: true, cancel: false,
    });
  });

  it("entregada o cancelada: nada", () => {
    for (const status of ["DELIVERED", "CANCELLED"] as const) {
      expect(Object.values(receptionActions(order(status, { lines: [line({ approved: false })] }))).some(Boolean)).toBe(false);
    }
  });
});

describe("líneas", () => {
  it("dice dónde está cada una", () => {
    expect(lineState(line({ approved: false }))).toBe("Por aprobar");
    expect(lineState(line({ approved: false, is_service: true }))).toBe("Por aprobar");
    expect(lineState(line({ is_service: true }))).toBe("Aprobada");
    expect(lineState(line())).toBe("Aprobado");
    expect(lineState(line({ taken: true }))).toBe("En la moto");
    expect(lineState(line({ taken: true, returned: true }))).toBe("Regresado");
  });

  it("encuentra la mano de obra por aprobar sin precio", () => {
    const free = line({ id: 3, is_service: true, approved: false, unit_price: "0.00", name: "Mano de obra" });
    expect(unpricedLabor([line(), line({ id: 2, is_service: true, unit_price: "0.00" }), free])).toBe(free);
    expect(unpricedLabor([line({ is_service: true, approved: false, unit_price: "25000.00" }), line({ unit_price: "0.00", approved: false })])).toBeNull();
  });
});

describe("recibir la moto", () => {
  const form = { ...emptyReceive(), mileage: "15400", request: "Cambio de aceite" };

  it("pide kilometraje en números y lo que pide el cliente", () => {
    expect(receiveProblem(emptyReceive(), 0)).toBe("Escribe el kilometraje con que llega.");
    expect(receiveProblem({ ...form, mileage: "15.400" }, 0)).toBe("Escribe el kilometraje con que llega.");
    expect(receiveProblem({ ...form, request: "  " }, 15200)).toBe("Escribe lo que pide el cliente.");
    expect(receiveProblem(form, 15200)).toBeNull();
    expect(receiveProblem(form, 15400)).toBeNull();
  });

  it("si el kilometraje baja, pide la nota", () => {
    expect(receiveProblem(form, 15401)).toBe("El kilometraje es menor que el que tenía: explica por qué.");
    expect(receiveProblem({ ...form, mileageNote: "Cambio de tablero" }, 15401)).toBeNull();
  });

  it("arma el cuerpo de la API", () => {
    expect(receivePayload(7, { mileage: " 15400 ", mileageNote: " ", request: " Aceite ", condition: " Casco ", mechanic: "3" })).toEqual({
      motorcycle: 7, mileage: 15400, mileage_note: "", request: "Aceite", condition: "Casco", mechanic: 3,
    });
    expect(receivePayload(7, form).mechanic).toBeNull();
  });
});
