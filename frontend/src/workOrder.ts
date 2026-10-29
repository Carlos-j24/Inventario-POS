// Órdenes de trabajo (spec 011), sin React para poder probarlo. El servidor (workshop/work_orders.py)
// decide: aquí solo se muestra lo que tiene sentido según el estado y se avisa antes de enviar.
import type { ApprovalChannel, WorkOrderDetail, WorkOrderLine, WorkOrderStatus } from "./api";
import { toCents } from "./money";

export const STATUS_LABELS: Record<WorkOrderStatus, string> = {
  RECEIVED: "Recibida",
  AWAITING_APPROVAL: "Esperando aprobación",
  IN_REPAIR: "En reparación",
  READY: "Lista",
  DELIVERED: "Entregada",
  CANCELLED: "Cancelada",
};

export const CHANNEL_LABELS: Record<ApprovalChannel, string> = { IN_PERSON: "En persona", PHONE: "Por llamada" };

/** Filtros de la lista: "" son las abiertas (lo que da la API sin ?status=) y ALL, todas. */
export const STATUS_FILTERS: [string, string][] = [
  ["", "Abiertas"],
  ...(Object.entries(STATUS_LABELS) as [string, string][]),
  ["ALL", "Todas"],
];

const OPEN: WorkOrderStatus[] = ["RECEIVED", "AWAITING_APPROVAL", "IN_REPAIR", "READY"];
const EDITABLE: WorkOrderStatus[] = ["RECEIVED", "AWAITING_APPROVAL", "IN_REPAIR"];

export const isOpen = (status: WorkOrderStatus) => OPEN.includes(status);
/** Aún se le agregan o quitan repuestos y mano de obra. */
export const isEditable = (status: WorkOrderStatus) => EDITABLE.includes(status);

/** Qué puede hacer recepción con la orden en su estado actual. */
export function receptionActions(order: WorkOrderDetail) {
  const pending = order.lines.some((l) => !l.approved);
  return {
    assign: isOpen(order.status),
    editLines: isEditable(order.status),
    approve: isEditable(order.status) && pending,
    sendToTill: order.status === "READY" && !order.till_order && !order.sale,
    deliver: order.status === "READY" && !!order.sale,
    cancel: isOpen(order.status) && !order.sale,
  };
}

/** Qué puede hacer el mecánico con su orden (spec 011, regla 6). */
export function mechanicActions(order: WorkOrderDetail) {
  const pending = order.lines.some((l) => !l.approved);
  return {
    editLines: isEditable(order.status),
    askApproval: (order.status === "RECEIVED" || order.status === "IN_REPAIR") && pending,
    ready: order.status === "IN_REPAIR",
  };
}

/** El repuesto aprobado sale de la bodega solo con la orden en reparación. */
export const canTake = (order: WorkOrderDetail, line: WorkOrderLine) =>
  order.status === "IN_REPAIR" && !line.is_service && line.approved && !line.taken;

/** Lo que salió y no se usó vuelve mientras la orden se puede editar. */
export const canReturn = (order: WorkOrderDetail, line: WorkOrderLine) =>
  isEditable(order.status) && line.taken && !line.returned;

/** Por qué todavía no se puede marcar lista, como lo diría el servidor, o null. */
export function readyProblem(order: WorkOrderDetail): string | null {
  if (order.lines.some((l) => !l.approved)) return "Hay cambios sin aprobar: que el cliente los apruebe o quítalos.";
  const untaken = order.lines.find((l) => !l.is_service && !l.taken);
  return untaken ? `${untaken.name} está aprobado pero no ha salido de la bodega: sácalo o quítalo.` : null;
}

/** Dónde está la línea: por aprobar, aprobada, puesta en la moto o regresada a la bodega. */
export function lineState(line: WorkOrderLine): string {
  if (!line.approved) return "Por aprobar";
  if (line.is_service) return "Aprobada";
  if (line.returned) return "Regresado";
  return line.taken ? "En la moto" : "Aprobado";
}

/** La primera mano de obra sin precio: el servidor no deja aprobar con ella. */
export const unpricedLabor = (lines: WorkOrderLine[]) =>
  lines.find((l) => !l.approved && l.is_service && toCents(l.unit_price) === 0) ?? null;

export interface ReceiveForm {
  mileage: string;
  mileageNote: string;
  request: string;
  condition: string;
  mechanic: string;
}

export const emptyReceive = (): ReceiveForm => ({ mileage: "", mileageNote: "", request: "", condition: "", mechanic: "" });

/** Lo primero que falta para recibir la moto, o null. Bajar el kilometraje pide una nota, como en la ficha de la moto. */
export function receiveProblem(form: ReceiveForm, currentMileage: number): string | null {
  const mileage = form.mileage.trim();
  if (!/^\d+$/.test(mileage)) return "Escribe el kilometraje con que llega.";
  if (Number(mileage) < currentMileage && !form.mileageNote.trim()) {
    return "El kilometraje es menor que el que tenía: explica por qué.";
  }
  if (!form.request.trim()) return "Escribe lo que pide el cliente.";
  return null;
}

/** El cuerpo que espera POST /api/workshop/orders/. */
export function receivePayload(motorcycle: number, form: ReceiveForm) {
  return {
    motorcycle,
    mileage: Number(form.mileage.trim()),
    mileage_note: form.mileageNote.trim(),
    request: form.request.trim(),
    condition: form.condition.trim(),
    mechanic: form.mechanic ? Number(form.mechanic) : null,
  };
}
