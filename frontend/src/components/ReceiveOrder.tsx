import { useEffect, useState, type FormEvent } from "react";

import { api, type Person, type WorkOrderDetail } from "../api";
import { formatKm } from "../motorcycle";
import { emptyReceive, receivePayload, receiveProblem, type ReceiveForm } from "../workOrder";

export const ORDERS_URL = "/api/workshop/orders/";

/** Recibe una moto en el taller (spec 011, T5): abre su orden de trabajo. Se usa en Órdenes y en la ficha de la moto. */
export default function ReceiveOrder({ motorcycle, onReceived, onCancel }: {
  motorcycle: { id: number; mileage: number; label: string };
  onReceived: (order: WorkOrderDetail) => void;
  onCancel: () => void;
}) {
  const [form, setForm] = useState<ReceiveForm>(emptyReceive);
  const [mechanics, setMechanics] = useState<Person[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const problem = receiveProblem(form, motorcycle.mileage);
  const lower = /^\d+$/.test(form.mileage.trim()) && Number(form.mileage) < motorcycle.mileage;
  const set = (k: keyof ReceiveForm) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value });

  useEffect(() => {
    api<Person[]>(`${ORDERS_URL}mechanics/`).then(setMechanics).catch((e: Error) => setError(e.message));
  }, []);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (problem) return;
    setBusy(true);
    setError(null);
    try {
      onReceived(await api<WorkOrderDetail>(ORDERS_URL, { method: "POST", body: receivePayload(motorcycle.id, form) }));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="action-form" onSubmit={submit} aria-label="Recibir moto">
      <h3>Recibir {motorcycle.label}</h3>
      <label>
        Kilometraje de llegada
        <input inputMode="numeric" value={form.mileage} onChange={set("mileage")} placeholder={`Va en ${formatKm(motorcycle.mileage)}`} />
      </label>
      {lower && <label>Por qué baja el kilometraje<input value={form.mileageNote} onChange={set("mileageNote")} /></label>}
      <label>Qué pide el cliente<textarea value={form.request} onChange={set("request")} rows={2} placeholder="Cambio de aceite y revisar frenos" /></label>
      <label>
        Estado en que llega
        <textarea value={form.condition} onChange={set("condition")} rows={2} placeholder="Rayones, golpes, lo que falta y lo que deja (casco, documentos)" />
      </label>
      <label>
        Mecánico
        <select value={form.mechanic} onChange={set("mechanic")}>
          <option value="">Sin asignar</option>
          {mechanics.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
        </select>
      </label>
      {problem && <p className="muted small">{problem}</p>}
      {error && <p className="error" role="alert">{error}</p>}
      <div className="row">
        <button type="button" onClick={onCancel}>Cancelar</button>
        <button className="primary" disabled={busy || !!problem}>Abrir orden</button>
      </div>
    </form>
  );
}
