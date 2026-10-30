import { useCallback, useEffect, useState } from "react";

import { api, type WorkOrderDetail, type WorkOrderRow } from "../api";
import { useAuth } from "../auth";
import AddLine from "../components/AddWorkOrderLine";
import { ORDERS_URL as URL } from "../components/ReceiveOrder";
import { formatQty } from "../money";
import { describeMotorcycle, formatKm } from "../motorcycle";
import { STATUS_LABELS, canReturn, canTake, lineState, mechanicActions, readyProblem } from "../workOrder";

const BADGE: Record<string, string> = { READY: "badge ok", AWAITING_APPROVAL: "badge warn" };

/** Spec 011, T6: el mecánico lleva las órdenes que tiene asignadas. Precios, aprobación, caja y entrega son de recepción. */
export default function MyOrders() {
  const { user } = useAuth();
  const [rows, setRows] = useState<WorkOrderRow[] | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Las abiertas asignadas a quien entró (aunque también sea de recepción y pueda ver todas).
  const load = useCallback(() => {
    if (!user) return Promise.resolve();
    return api<WorkOrderRow[]>(`${URL}?mechanic=${user?.id}`).then((r) => { setRows(r); setError(null); }).catch((e: Error) => setError(e.message));
  }, [user?.id]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="two-cols">
      <section className="card">
        <h2>Mis órdenes</h2>
        {error && <p className="error" role="alert">{error}</p>}
        <table className="cart sales-list">
          <thead><tr><th>Orden</th><th>Moto</th><th>Pide</th><th>Estado</th></tr></thead>
          <tbody>
            {(rows ?? []).map((o) => (
              <tr key={o.id} className={o.id === selected ? "selected" : ""} onClick={() => setSelected(o.id)}>
                <td><button className="link" onClick={() => setSelected(o.id)}>{o.number}</button></td>
                <td>{describeMotorcycle(o.motorcycle)}</td>
                <td>{o.request}</td>
                <td><span className={BADGE[o.status] ?? "badge"}>{STATUS_LABELS[o.status]}</span></td>
              </tr>
            ))}
            {rows && rows.length === 0 && <tr><td colSpan={4} className="muted center">No tienes órdenes abiertas.</td></tr>}
          </tbody>
        </table>
      </section>
      <aside className="card">
        {selected === null ? <p className="muted">Elige una orden.</p> : <OrderCard key={selected} id={selected} onChanged={load} />}
      </aside>
    </div>
  );
}

function OrderCard({ id, onChanged }: { id: number; onChanged: () => void }) {
  const [order, setOrder] = useState<WorkOrderDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    api<WorkOrderDetail>(`${URL}${id}/`).then(setOrder).catch((e: Error) => setError(e.message));
  }, [id]);

  async function send(path: string, method: string, body: unknown, done: string): Promise<boolean> {
    setError(null);
    setMessage(null);
    try {
      setOrder(await api<WorkOrderDetail>(`${URL}${id}/${path}`, { method, body }));
      setMessage(done);
      onChanged();
      return true;
    } catch (err) {
      setError((err as Error).message);
      return false;
    }
  }

  if (!order) return error ? <p className="error" role="alert">{error}</p> : <p className="muted">Cargando…</p>;
  const can = mechanicActions(order);
  const notReady = readyProblem(order);

  return (
    <div className="action-form">
      <div className="row spread">
        <h2>{order.number} · {describeMotorcycle(order.motorcycle)}</h2>
        <span className={BADGE[order.status] ?? "badge"}>{STATUS_LABELS[order.status]}</span>
      </div>
      <p className="muted small">Llegó con {formatKm(order.mileage_in)}</p>
      <p><span className="muted">Pide:</span> {order.request}</p>
      {order.condition && <p><span className="muted">Estado al llegar:</span> {order.condition}</p>}
      {message && <p className="change" role="status">{message}</p>}
      {error && <p className="error" role="alert">{error}</p>}

      <h3>Diagnóstico</h3>
      {can.editLines ? (
        <Diagnosis key={order.diagnosis} current={order.diagnosis} onSave={(diagnosis) => send("diagnose/", "POST", { diagnosis }, "Diagnóstico guardado.")} />
      ) : (
        <p>{order.diagnosis || <em className="muted">sin diagnóstico</em>}</p>
      )}

      <h3>Repuestos y mano de obra</h3>
      {order.lines.length === 0 ? (
        <p className="muted small">Todavía sin repuestos ni mano de obra.</p>
      ) : (
        <table className="cart" aria-label="Repuestos y mano de obra">
          <thead><tr><th>Descripción</th><th className="num">Cant.</th><th>Estado</th><th /></tr></thead>
          <tbody>
            {order.lines.map((l) => (
              <tr key={l.id} className={l.approved ? "" : "pending"}>
                <td>{l.name} <span className="muted small">{l.is_service ? "mano de obra" : l.sku}</span></td>
                <td className="num">{formatQty(l.quantity)}</td>
                <td>{lineState(l)}</td>
                <td><span className="row">
                  {canTake(order, l) && (
                    <button onClick={() => send(`lines/${l.id}/take/`, "POST", {}, `${l.name} salió de la bodega.`)}>Sacar</button>
                  )}
                  {canReturn(order, l) && (
                    <button className="link" onClick={() => send(`lines/${l.id}/return/`, "POST", {}, `${l.name} volvió a la bodega.`)}>Regresar</button>
                  )}
                  {can.editLines && !l.taken && (
                    <button className="link" onClick={() => send(`lines/${l.id}/`, "DELETE", undefined, `${l.name} quitado.`)}>Quitar</button>
                  )}
                </span></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {order.status === "AWAITING_APPROVAL" && <p className="muted small">Esperando que el cliente apruebe: recepción lo registra.</p>}
      {order.status === "IN_REPAIR" && order.lines.some((l) => !l.approved) && (
        <p className="muted small">Lo agregado después de aprobar no sale de la bodega hasta que el cliente lo apruebe.</p>
      )}
      {can.editLines && <AddLine onAdd={(body, name) => send("lines/", "POST", body, `${name} agregado: queda por aprobar.`)} />}

      <div className="row">
        {can.askApproval && (
          <button onClick={() => send("send-for-approval/", "POST", {}, "Pedida la aprobación: recepción se la muestra al cliente.")}>
            Pedir aprobación
          </button>
        )}
        {can.ready && (
          <button className="primary" disabled={!!notReady} onClick={() => send("ready/", "POST", {}, "Orden lista: recepción la cobra y la entrega.")}>
            Marcar lista
          </button>
        )}
      </div>
      {can.ready && notReady && <p className="muted small">{notReady}</p>}
    </div>
  );
}

function Diagnosis({ current, onSave }: { current: string; onSave: (diagnosis: string) => Promise<boolean> }) {
  const [value, setValue] = useState(current);
  return (
    <div className="action-form">
      <textarea value={value} onChange={(e) => setValue(e.target.value)} rows={3} aria-label="Diagnóstico" placeholder="Qué tiene la moto y qué hay que hacerle" />
      <div className="row">
        <button disabled={value.trim() === current.trim()} onClick={() => onSave(value.trim())}>Guardar diagnóstico</button>
      </div>
    </div>
  );
}
