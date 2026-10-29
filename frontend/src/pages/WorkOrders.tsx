import { useCallback, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";

import {
  api, type ApprovalChannel, type Business, type Motorcycle, type Person, type WorkOrderDetail,
  type WorkOrderLine, type WorkOrderRow,
} from "../api";
import AddLine from "../components/AddWorkOrderLine";
import ReceiveOrder, { ORDERS_URL as URL } from "../components/ReceiveOrder";
import WorkOrderPrint from "../components/WorkOrderPrint";
import { formatMoney, formatQty, toCents } from "../money";
import { describeMotorcycle, formatKm, normalizeCode } from "../motorcycle";
import {
  CHANNEL_LABELS, STATUS_FILTERS, STATUS_LABELS, lineState, receptionActions, unpricedLabor,
} from "../workOrder";

const money = (value: string) => formatMoney(toCents(value));
const when = (iso: string) => new Date(iso).toLocaleString("es-CO", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
const BADGE: Record<string, string> = { READY: "badge ok", AWAITING_APPROVAL: "badge warn", CANCELLED: "badge danger" };

/** Spec 011, T5: recepción del taller recibe motos y lleva sus órdenes hasta entregarlas. */
export default function WorkOrders() {
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [rows, setRows] = useState<WorkOrderRow[] | null>(null);
  const [selected, setSelected] = useState<number | "new" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    const params = status ? `?status=${status}` : "";
    return api<WorkOrderRow[]>(`${URL}${params}`).then((r) => { setRows(r); setError(null); }).catch((e: Error) => setError(e.message));
  }, [status]);

  useEffect(() => { load(); }, [load]);

  // La lista trae hasta 100: se busca en ella por número, placa o cliente.
  const shown = useMemo(() => {
    const term = q.trim().toLowerCase();
    if (!term) return rows ?? [];
    const code = normalizeCode(term);
    return (rows ?? []).filter((o) =>
      o.number.toLowerCase().includes(term) || (code && normalizeCode(o.motorcycle.plate).includes(code)) ||
      o.customer.name.toLowerCase().includes(term) || o.customer.phone.includes(term));
  }, [rows, q]);

  return (
    <div className="two-cols">
      <section className="card">
        <div className="row spread">
          <h2>Órdenes de trabajo</h2>
          <button className="primary" onClick={() => setSelected("new")}>Recibir moto</button>
        </div>
        <div className="row filters">
          <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Estado">
            {STATUS_FILTERS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
          <input placeholder="Número, placa o cliente" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Buscar orden" />
        </div>
        {error && <p className="error" role="alert">{error}</p>}
        <table className="cart sales-list">
          <thead><tr><th>Orden</th><th>Moto</th><th>Cliente</th><th>Mecánico</th><th>Estado</th></tr></thead>
          <tbody>
            {shown.map((o) => (
              <tr key={o.id} className={o.id === selected ? "selected" : ""} onClick={() => setSelected(o.id)}>
                <td><button className="link" onClick={() => setSelected(o.id)}>{o.number}</button></td>
                <td>{describeMotorcycle(o.motorcycle)}</td>
                <td>{o.customer.name} <span className="muted small">{o.customer.phone}</span></td>
                <td>{o.mechanic?.name ?? <span className="muted">Sin asignar</span>}</td>
                <td><span className={BADGE[o.status] ?? "badge"}>{STATUS_LABELS[o.status]}</span></td>
              </tr>
            ))}
            {rows && shown.length === 0 && (
              <tr><td colSpan={5} className="muted center">{q.trim() ? "Ninguna orden coincide." : "No hay órdenes en este estado."}</td></tr>
            )}
          </tbody>
        </table>
      </section>
      <aside className="card">
        {selected === "new" && (
          <FindAndReceive onReceived={(o) => { load(); setSelected(o.id); }} onCancel={() => setSelected(null)} />
        )}
        {typeof selected === "number" && <OrderCard key={selected} id={selected} onChanged={load} />}
        {selected === null && <p className="muted">Elige una orden o recibe una moto.</p>}
      </aside>
    </div>
  );
}

/** Busca la moto (como en la pantalla Motos) y la recibe. Si no está registrada, se registra allá. */
function FindAndReceive({ onReceived, onCancel }: { onReceived: (o: WorkOrderDetail) => void; onCancel: () => void }) {
  const [q, setQ] = useState("");
  const [found, setFound] = useState<Motorcycle[] | null>(null);
  const [moto, setMoto] = useState<Motorcycle | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!q.trim()) { setFound(null); return; }
    const timer = setTimeout(() => {
      api<Motorcycle[]>(`/api/workshop/motorcycles/?${new URLSearchParams({ q: q.trim() })}`)
        .then((r) => { setFound(r); setError(null); }).catch((e: Error) => setError(e.message));
    }, 250);
    return () => clearTimeout(timer);
  }, [q]);

  if (moto) {
    return (
      <ReceiveOrder
        motorcycle={{ id: moto.id, mileage: moto.mileage, label: describeMotorcycle(moto) }}
        onReceived={onReceived}
        onCancel={() => setMoto(null)}
      />
    );
  }
  return (
    <div className="action-form">
      <h2>Recibir moto</h2>
      <input placeholder="Placa, chasis, cédula, teléfono o nombre" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Buscar moto" autoFocus />
      {error && <p className="error" role="alert">{error}</p>}
      <ul className="plain-list" aria-label="Motos encontradas">
        {(found ?? []).map((m) => (
          <li key={m.id}>
            <button className="link" onClick={() => setMoto(m)}>{describeMotorcycle(m)}</button>
            <span className="muted small"> · {m.owner.name} · {formatKm(m.mileage)}</span>
          </li>
        ))}
      </ul>
      {found && found.length === 0 && <p className="muted small">Ninguna moto coincide. Si es nueva, regístrala primero en Motos.</p>}
      <div className="row"><button type="button" onClick={onCancel}>Cancelar</button></div>
    </div>
  );
}

function OrderCard({ id, onChanged }: { id: number; onChanged: () => void }) {
  const [order, setOrder] = useState<WorkOrderDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [printing, setPrinting] = useState(false);

  useEffect(() => {
    api<WorkOrderDetail>(`${URL}${id}/`).then(setOrder).catch((e: Error) => setError(e.message));
  }, [id]);

  /** Envía un cambio y muestra la ficha que devuelve el servidor. Dice si salió bien. */
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
  const can = receptionActions(order);

  return (
    <div className="action-form">
      <div className="row spread">
        <h2>{order.number} · {describeMotorcycle(order.motorcycle)}</h2>
        <span className={BADGE[order.status] ?? "badge"}>{STATUS_LABELS[order.status]}</span>
      </div>
      <p>
        Cliente: <strong>{order.customer.name}</strong> · {order.customer.phone}
        <span className="muted small"> · llegó con {formatKm(order.mileage_in)}
          {order.mileage_out != null && `, salió con ${formatKm(order.mileage_out)}`}</span>
      </p>
      <p><span className="muted">Pide:</span> {order.request}</p>
      {order.condition && <p><span className="muted">Estado al llegar:</span> {order.condition}</p>}
      <p><span className="muted">Diagnóstico:</span> {order.diagnosis || <em className="muted">todavía sin diagnóstico</em>}</p>
      {message && <p className="change" role="status">{message}</p>}
      {error && <p className="error" role="alert">{error}</p>}

      <h3>Mecánico</h3>
      {can.assign ? (
        <Assign current={order.mechanic} onSave={(mechanic) =>
          send("assign/", "POST", { mechanic: mechanic?.id ?? null }, mechanic ? `Asignada a ${mechanic.name}.` : "Quedó sin mecánico.")} />
      ) : (
        <p>{order.mechanic?.name ?? "Sin asignar"}</p>
      )}

      <h3>Presupuesto</h3>
      <Lines order={order} editable={can.editLines} send={send} />
      {can.editLines && <AddLine canPrice onAdd={(body, name) => send("lines/", "POST", body, `${name} agregado: queda por aprobar.`)} />}
      <div className="row">
        <button type="button" onClick={() => setPrinting(true)}>Imprimir presupuesto</button>
      </div>
      {printing && <PrintDialog order={order} onClose={() => setPrinting(false)} />}

      {can.approve && (
        <Approve order={order} onSave={(body) => send("approve/", "POST", body, `Aprobado por ${body.approved_by.trim()}: pasa a reparación.`)} />
      )}
      {order.approvals.length > 0 && (
        <ul className="plain-list small" aria-label="Aprobaciones">
          {order.approvals.map((a, i) => (
            <li key={i}>{when(a.recorded_at)}: aprobó {a.approved_by} ({CHANNEL_LABELS[a.channel].toLowerCase()}) por {money(a.total)}
              <span className="muted"> · registró {a.recorded_by}</span></li>
          ))}
        </ul>
      )}

      {(order.status === "READY" || order.till_order || order.sale) && <h3>Cobro y entrega</h3>}
      {order.till_order && (
        <p className="change">En la caja: pedido <strong>{order.till_order.code}</strong> por {money(order.till_order.total)}.</p>
      )}
      {order.sale && <p>Cobrada en la venta {order.sale.number} por {money(order.sale.total)}.</p>}
      {can.sendToTill && (
        <button className="primary" onClick={() => send("send-to-till/", "POST", {}, "Mandada a la caja: cóbrala con el código del pedido.")}>
          Mandar a la caja ({money(order.charged_total)})
        </button>
      )}
      {order.status === "READY" && !order.sale && <p className="muted small">La moto se entrega cuando la caja cobre el pedido.</p>}
      {can.deliver && <Deliver mileageIn={order.mileage_in} onSave={(body) => send("deliver/", "POST", body, "Moto entregada.")} />}

      {can.cancel && <Cancel onSave={(reason) => send("cancel/", "POST", { reason }, "Orden cancelada: los repuestos que salieron volvieron a la bodega.")} />}

      <h3>Historia</h3>
      <ul className="plain-list small" aria-label="Historia de la orden">
        {order.events.map((e, i) => (
          <li key={i}>{when(e.at)}: {STATUS_LABELS[e.status]} <span className="muted">({e.user})</span>{e.note && <> · <em>{e.note}</em></>}</li>
        ))}
      </ul>
    </div>
  );
}

function Assign({ current, onSave }: { current: Person | null; onSave: (m: Person | null) => Promise<boolean> }) {
  const [mechanics, setMechanics] = useState<Person[]>([]);
  useEffect(() => { api<Person[]>(`${URL}mechanics/`).then(setMechanics).catch(() => setMechanics([])); }, []);
  // Si el asignado ya no es mecánico activo, igual se muestra.
  const options = current && !mechanics.some((m) => m.id === current.id) ? [current, ...mechanics] : mechanics;
  return (
    <select
      value={current?.id ?? ""}
      aria-label="Mecánico asignado"
      onChange={(e) => onSave(options.find((m) => m.id === Number(e.target.value)) ?? null)}
    >
      <option value="">Sin asignar</option>
      {options.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
    </select>
  );
}

type Send = (path: string, method: string, body: unknown, done: string) => Promise<boolean>;

function Lines({ order, editable, send }: { order: WorkOrderDetail; editable: boolean; send: Send }) {
  if (!order.lines.length) return <p className="muted small">Todavía sin repuestos ni mano de obra.</p>;
  return (
    <table className="cart" aria-label="Líneas del presupuesto">
      <thead><tr><th>Descripción</th><th className="num">Cant.</th><th className="num">Precio</th><th className="num">Total</th><th>Estado</th><th /></tr></thead>
      <tbody>
        {order.lines.map((l) => (
          <tr key={l.id} className={l.approved ? "" : "pending"}>
            <td>{l.name} <span className="muted small">{l.is_service ? "mano de obra" : l.sku}</span></td>
            <td className="num">{formatQty(l.quantity)}</td>
            <td className="num">
              {editable && l.is_service && !l.approved ? <LaborPrice line={l} send={send} /> : money(l.unit_price)}
            </td>
            <td className="num">{money(l.total)}</td>
            <td>{lineState(l)}</td>
            <td>
              {editable && !l.taken && (
                <button className="link" onClick={() => send(`lines/${l.id}/`, "DELETE", undefined, `${l.name} quitado.`)}>Quitar</button>
              )}
            </td>
          </tr>
        ))}
      </tbody>
      <tfoot>
        <tr><td colSpan={3}>Aprobado</td><td className="num">{money(order.charged_total)}</td><td colSpan={2} /></tr>
        {toCents(order.pending_total) > 0 && (
          <tr><td colSpan={3}>Por aprobar</td><td className="num">{money(order.pending_total)}</td><td colSpan={2} /></tr>
        )}
      </tfoot>
    </table>
  );
}

/** Recepción le pone precio a la mano de obra antes de que el cliente la apruebe. */
function LaborPrice({ line, send }: { line: WorkOrderLine; send: Send }) {
  const [value, setValue] = useState(toCents(line.unit_price) ? String(toCents(line.unit_price) / 100) : "");
  const valid = /^\d+$/.test(value.trim());
  const changed = valid && Number(value) * 100 !== toCents(line.unit_price);
  return (
    <span className="row">
      <input inputMode="numeric" value={value} onChange={(e) => setValue(e.target.value)} aria-label={`Precio de ${line.name}`} size={8} />
      {changed && (
        <button className="link" onClick={() => send(`lines/${line.id}/`, "PATCH", { unit_price: value.trim() }, `Precio de ${line.name} guardado.`)}>
          Guardar
        </button>
      )}
    </span>
  );
}

function Approve({ order, onSave }: { order: WorkOrderDetail; onSave: (body: { approved_by: string; channel: ApprovalChannel }) => Promise<boolean> }) {
  const [approvedBy, setApprovedBy] = useState(order.customer.name);
  const [channel, setChannel] = useState<ApprovalChannel>("PHONE");
  const free = unpricedLabor(order.lines);
  return (
    <div className="action-form" aria-label="Aprobación del cliente">
      <h3>Aprobación del cliente ({money(order.pending_total)})</h3>
      <div className="row">
        <label>Quién aprobó<input value={approvedBy} onChange={(e) => setApprovedBy(e.target.value)} /></label>
        <label>
          Cómo
          <select value={channel} onChange={(e) => setChannel(e.target.value as ApprovalChannel)}>
            {(Object.entries(CHANNEL_LABELS) as [ApprovalChannel, string][]).map(([v, label]) => <option key={v} value={v}>{label}</option>)}
          </select>
        </label>
      </div>
      {free && <p className="muted small">Ponle precio a {free.name} antes de aprobar.</p>}
      <button className="primary" disabled={!approvedBy.trim() || !!free} onClick={() => onSave({ approved_by: approvedBy, channel })}>
        Registrar aprobación
      </button>
    </div>
  );
}

function Deliver({ mileageIn, onSave }: { mileageIn: number; onSave: (body: { mileage: number | null; mileage_note: string }) => Promise<boolean> }) {
  const [mileage, setMileage] = useState("");
  const [note, setNote] = useState("");
  const valid = !mileage.trim() || /^\d+$/.test(mileage.trim());
  const lower = valid && !!mileage.trim() && Number(mileage) < mileageIn;
  return (
    <div className="action-form" aria-label="Entregar moto">
      <label>
        Kilometraje de salida (si cambió)
        <input inputMode="numeric" value={mileage} onChange={(e) => setMileage(e.target.value)} placeholder={`Llegó con ${formatKm(mileageIn)}`} />
      </label>
      {lower && <label>Por qué baja el kilometraje<input value={note} onChange={(e) => setNote(e.target.value)} /></label>}
      <button
        className="primary"
        disabled={!valid || (lower && !note.trim())}
        onClick={() => onSave({ mileage: mileage.trim() ? Number(mileage) : null, mileage_note: note.trim() })}
      >
        Entregar moto
      </button>
    </div>
  );
}

function Cancel({ onSave }: { onSave: (reason: string) => Promise<boolean> }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  if (!open) return <div className="row"><button className="danger-btn" onClick={() => setOpen(true)}>Cancelar orden</button></div>;
  return (
    <div className="action-form" aria-label="Cancelar orden">
      <label>Por qué se cancela<input value={reason} onChange={(e) => setReason(e.target.value)} /></label>
      <p className="muted small">Los repuestos que ya salieron vuelven a la bodega y el pedido sale de la caja.</p>
      <div className="row">
        <button type="button" onClick={() => setOpen(false)}>No cancelar</button>
        <button className="danger-btn" disabled={!reason.trim()} onClick={() => onSave(reason.trim())}>Cancelar la orden</button>
      </div>
    </div>
  );
}

function PrintDialog({ order, onClose }: { order: WorkOrderDetail; onClose: () => void }) {
  const [business, setBusiness] = useState<Business | null>(null);
  useEffect(() => { api<Business | null>("/api/invoicing/business/").then(setBusiness).catch(() => setBusiness(null)); }, []);
  return createPortal(
    <div className="overlay print-portal" role="dialog" aria-label="Imprimir presupuesto">
      <div className="card modal quote-modal">
        <WorkOrderPrint order={order} business={business} />
        <div className="row no-print">
          <button type="button" className="primary" onClick={() => window.print()}>Imprimir</button>
          <button type="button" onClick={onClose}>Cerrar</button>
        </div>
        <p className="muted small no-print">Para el PDF, elige "Guardar como PDF" en la impresora.</p>
      </div>
    </div>,
    document.body,
  );
}
