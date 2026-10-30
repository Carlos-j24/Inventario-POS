import { useCallback, useEffect, useState, type FormEvent } from "react";

import { api, type Business, type MaintenancePlan, type MaintenanceRow, type NoticeChannel, type Product } from "../api";
import { useCan } from "../auth";
import ProductSearch from "../components/ProductSearch";
import {
  REMINDER_LABELS, dueLabel, emptyPlan, planForm, planInterval, planPayload, planProblem, whatsappLink, whatsappMessage,
  type PlanForm,
} from "../maintenance";
import { describeMotorcycle, formatKm } from "../motorcycle";
import { todayIso } from "./Sales";

const DUE = "/api/workshop/maintenance/";
const PLANS = "/api/workshop/plans/";
const when = (iso: string) => new Date(iso).toLocaleString("es-CO", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
const CHANNELS: Record<NoticeChannel, string> = { WHATSAPP: "WhatsApp", PHONE: "llamada" };

/** Spec 012, T4: recepción avisa los mantenimientos que vencen; quien maneja el catálogo define los planes. */
export default function Maintenance() {
  const can = useCan();
  const tabs = [
    can("workshop.receive") && { id: "due", label: "Por vencer" },
    can("catalog.edit") && { id: "plans", label: "Planes" },
  ].filter(Boolean) as { id: string; label: string }[];
  const [chosen, setChosen] = useState<string | null>(null);
  // La sesión puede cargar después: la pestaña se decide en cada render con los permisos que haya.
  const tab = (tabs.find((t) => t.id === chosen) ?? tabs[0])?.id;

  return (
    <div>
      {tabs.length > 1 && (
        <div className="row">
          {tabs.map((t) => (
            <button key={t.id} className={t.id === tab ? "tab active" : "tab"} aria-pressed={t.id === tab} onClick={() => setChosen(t.id)}>
              {t.label}
            </button>
          ))}
        </div>
      )}
      {tab === "due" && <DueList />}
      {tab === "plans" && <Plans />}
    </div>
  );
}

function DueList() {
  const [plans, setPlans] = useState<MaintenancePlan[]>([]);
  const [plan, setPlan] = useState("");
  const [notified, setNotified] = useState(false);
  const [rows, setRows] = useState<MaintenanceRow[] | null>(null);
  const [selected, setSelected] = useState<MaintenanceRow | null>(null);
  const [business, setBusiness] = useState("el taller");
  const [error, setError] = useState<string | null>(null);
  const today = todayIso();

  useEffect(() => {
    api<MaintenancePlan[]>(PLANS).then(setPlans).catch(() => setPlans([]));
    api<Business | null>("/api/invoicing/business/").then((b) => b && setBusiness(b.trade_name || b.name || "el taller")).catch(() => {});
  }, []);

  const load = useCallback(() => {
    const params = new URLSearchParams();
    if (plan) params.set("plan", plan);
    if (notified) params.set("notified", "1");
    return api<MaintenanceRow[]>(`${DUE}?${params}`).then((r) => { setRows(r); setError(null); }).catch((e: Error) => setError(e.message));
  }, [plan, notified]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="two-cols">
      <section className="card">
        <h2>Mantenimientos por vencer</h2>
        <div className="row filters">
          <select value={plan} onChange={(e) => setPlan(e.target.value)} aria-label="Plan">
            <option value="">Todos los planes</option>
            {plans.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          <label className="check">
            <input type="checkbox" checked={notified} onChange={(e) => setNotified(e.target.checked)} /> Ver también los avisados
          </label>
        </div>
        {error && <p className="error" role="alert">{error}</p>}
        <table className="cart sales-list maintenance-list">
          <thead><tr><th>Moto</th><th>Dueño</th><th>Plan</th><th>Vence</th><th>Estado</th></tr></thead>
          <tbody>
            {(rows ?? []).map((r) => (
              <tr key={r.id} className={r.id === selected?.id ? "selected" : ""} onClick={() => setSelected(r)}>
                <td><button className="link" onClick={() => setSelected(r)}>{describeMotorcycle(r.motorcycle)}</button></td>
                <td>{r.owner.name} <span className="muted small">{r.owner.phone}</span></td>
                <td>{r.plan.name}</td>
                <td className={r.due_on && r.due_on < today ? "error" : ""}>{dueLabel(r, today)}</td>
                <td><span className={r.status === "NOTIFIED" ? "badge ok" : "badge warn"}>{REMINDER_LABELS[r.status]}</span></td>
              </tr>
            ))}
            {rows && rows.length === 0 && (
              <tr><td colSpan={5} className="muted center">No hay mantenimientos por vencer esta semana.</td></tr>
            )}
          </tbody>
        </table>
      </section>
      <aside className="card">
        {selected ? (
          <ReminderCard key={selected.id} row={selected} business={business} today={today}
            onChanged={(r) => { setSelected(r); load(); }} />
        ) : (
          <p className="muted">Elige un mantenimiento para avisarle al cliente.</p>
        )}
      </aside>
    </div>
  );
}

function ReminderCard({ row, business, today, onChanged }: {
  row: MaintenanceRow; business: string; today: string; onChanged: (row: MaintenanceRow) => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const open = row.status === "PENDING" || row.status === "NOTIFIED";
  const link = whatsappLink(row.owner.phone, whatsappMessage(row, business));

  async function send(action: string, body: unknown, done: string): Promise<boolean> {
    setError(null);
    setMessage(null);
    try {
      onChanged(await api<MaintenanceRow>(`${DUE}${row.id}/${action}/`, { method: "POST", body }));
      setMessage(done);
      return true;
    } catch (err) {
      setError((err as Error).message);
      return false;
    }
  }

  return (
    <div className="action-form">
      <h2>{describeMotorcycle(row.motorcycle)}</h2>
      <p>Dueño: <strong>{row.owner.name}</strong> · {row.owner.phone || <em className="muted">sin teléfono</em>}</p>
      <p>
        {row.plan.name}: <strong>{dueLabel(row, today)}</strong>
        <span className="muted small">
          {row.due_date && ` · fecha del plan ${row.due_date}`}
          {row.due_mileage != null && ` · a los ${formatKm(row.due_mileage)}`}
          {` · va en ${formatKm(row.motorcycle.mileage)}`}
          {row.daily_km && ` · anda unos ${Number(row.daily_km).toLocaleString("es-CO")} km al día`}
        </span>
      </p>
      <p className="muted small">De la orden {row.source_order}{row.note && <> · <em>{row.note}</em></>}</p>
      {message && <p className="change" role="status">{message}</p>}
      {error && <p className="error" role="alert">{error}</p>}

      {open && (
        <>
          <h3>Avisar</h3>
          {link ? (
            <a className="link-button primary" href={link} target="_blank" rel="noopener noreferrer">Escribir por WhatsApp</a>
          ) : (
            <p className="muted small">El teléfono no es un celular: avisa por llamada.</p>
          )}
          <div className="row">
            <button onClick={() => send("notify", { channel: "WHATSAPP" }, "Quedó avisado por WhatsApp.")}>Avisado por WhatsApp</button>
            <button onClick={() => send("notify", { channel: "PHONE" }, "Quedó avisado por llamada.")}>Avisado por llamada</button>
          </div>
        </>
      )}
      {row.notices.length > 0 && (
        <ul className="plain-list small" aria-label="Avisos">
          {row.notices.map((n, i) => <li key={i}>{when(n.at)}: por {CHANNELS[n.channel]} <span className="muted">({n.user})</span></li>)}
        </ul>
      )}
      {open && <Adjust row={row} onSave={(body) => send("adjust", body, "Recordatorio ajustado.")} />}
      {open && <Dismiss onSave={(note) => send("dismiss", { note }, "Recordatorio descartado: sale de la lista.")} />}
      {!open && <p className="muted">Este recordatorio está {REMINDER_LABELS[row.status].toLowerCase()}.</p>}
    </div>
  );
}

function Adjust({ row, onSave }: { row: MaintenanceRow; onSave: (body: { due_date: string | null; due_mileage: number | null; note: string }) => Promise<boolean> }) {
  const [openForm, setOpenForm] = useState(false);
  const [date, setDate] = useState(row.due_date ?? "");
  const [km, setKm] = useState(row.due_mileage?.toString() ?? "");
  const [note, setNote] = useState("");
  const validKm = !km.trim() || (/^\d+$/.test(km.trim()) && Number(km) > 0);
  const ready = validKm && (!!date || !!km.trim()) && !!note.trim();
  if (!openForm) return <div className="row"><button className="link" onClick={() => setOpenForm(true)}>Ajustar fecha o kilometraje</button></div>;
  return (
    <form className="action-form" aria-label="Ajustar" onSubmit={(e: FormEvent) => {
      e.preventDefault();
      if (ready) onSave({ due_date: date || null, due_mileage: km.trim() ? Number(km) : null, note: note.trim() });
    }}>
      <div className="row">
        <label>Vence el<input type="date" value={date} onChange={(e) => setDate(e.target.value)} /></label>
        <label>A los km<input inputMode="numeric" value={km} onChange={(e) => setKm(e.target.value)} /></label>
      </div>
      <label>Por qué<input value={note} onChange={(e) => setNote(e.target.value)} placeholder="El cliente dijo que viene en diciembre" /></label>
      {!validKm && <p className="muted small">Los km van en números mayores que cero.</p>}
      <div className="row">
        <button type="button" onClick={() => setOpenForm(false)}>Cancelar</button>
        <button className="primary" disabled={!ready}>Guardar ajuste</button>
      </div>
    </form>
  );
}

function Dismiss({ onSave }: { onSave: (note: string) => Promise<boolean> }) {
  const [openForm, setOpenForm] = useState(false);
  const [note, setNote] = useState("");
  if (!openForm) return <div className="row"><button className="danger-btn" onClick={() => setOpenForm(true)}>Descartar</button></div>;
  return (
    <div className="action-form" aria-label="Descartar">
      <label>Por qué se descarta<input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Vendió la moto" /></label>
      <div className="row">
        <button type="button" onClick={() => setOpenForm(false)}>No descartar</button>
        <button className="danger-btn" disabled={!note.trim()} onClick={() => onSave(note.trim())}>Descartar recordatorio</button>
      </div>
    </div>
  );
}

// --- Planes -------------------------------------------------------------------------

function Plans() {
  const [plans, setPlans] = useState<MaintenancePlan[] | null>(null);
  const [selected, setSelected] = useState<MaintenancePlan | "new" | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => api<MaintenancePlan[]>(PLANS).then(setPlans).catch((e: Error) => setError(e.message)), []);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="two-cols">
      <section className="card">
        <div className="row spread">
          <h2>Planes de mantenimiento</h2>
          <button className="primary" onClick={() => { setNotice(null); setSelected("new"); }}>Nuevo plan</button>
        </div>
        {error && <p className="error" role="alert">{error}</p>}
        <table className="cart sales-list">
          <thead><tr><th>Plan</th><th>Cada</th><th>Lo cumplen</th></tr></thead>
          <tbody>
            {(plans ?? []).map((p) => (
              <tr key={p.id} className={!p.is_active ? "voided" : ""} onClick={() => { setNotice(null); setSelected(p); }}>
                <td><button className="link" onClick={() => { setNotice(null); setSelected(p); }}>{p.name}</button>{!p.is_active && <span className="muted small"> · inactivo</span>}</td>
                <td>{planInterval(p)}</td>
                <td className="small">{p.product_list.map((x) => x.name).join(", ")}</td>
              </tr>
            ))}
            {plans && plans.length === 0 && (
              <tr><td colSpan={3} className="muted center">Todavía no hay planes. Crea uno, p. ej. "Cambio de aceite".</td></tr>
            )}
          </tbody>
        </table>
      </section>
      <aside className="card">
        {notice && <p className="change" role="status">{notice}</p>}
        {selected ? (
          <PlanEditor key={selected === "new" ? "new" : selected.id} plan={selected === "new" ? null : selected}
            onSaved={(p, done) => { load(); setSelected(p); setNotice(done); }} onCancel={() => setSelected(null)} />
        ) : (
          <p className="muted">Al entregar una moto con un producto de un plan, se calcula su próximo mantenimiento.</p>
        )}
      </aside>
    </div>
  );
}

function PlanEditor({ plan, onSaved, onCancel }: {
  plan: MaintenancePlan | null; onSaved: (p: MaintenancePlan, done: string) => void; onCancel: () => void;
}) {
  const [form, setForm] = useState<PlanForm>(() => (plan ? planForm(plan) : emptyPlan()));
  const [products, setProducts] = useState<Product[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const problem = planProblem(form);
  const set = (k: "name" | "everyKm" | "everyDays") => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value });

  useEffect(() => { api<Product[]>("/api/catalog/products/").then(setProducts).catch(() => setProducts([])); }, []);

  async function submit() {
    if (problem) return;
    setBusy(true);
    setError(null);
    try {
      const saved = await api<MaintenancePlan>(plan ? `${PLANS}${plan.id}/` : PLANS, { method: plan ? "PATCH" : "POST", body: planPayload(form) });
      onSaved(saved, plan ? "Plan guardado." : "Plan creado.");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    // Sin <form>: el buscador de productos trae el suyo y no se pueden anidar.
    <div className="action-form" role="form" aria-label="Plan">
      <h2>{plan ? plan.name : "Nuevo plan"}</h2>
      <label>Nombre<input value={form.name} onChange={set("name")} placeholder="Cambio de aceite" /></label>
      <div className="row">
        <label>Cada cuántos km<input inputMode="numeric" value={form.everyKm} onChange={set("everyKm")} placeholder="3000" /></label>
        <label>Cada cuántos días<input inputMode="numeric" value={form.everyDays} onChange={set("everyDays")} placeholder="90" /></label>
      </div>
      <p className="muted small">Pon uno o los dos: vence con lo primero que llegue.</p>
      <h3>Lo cumplen</h3>
      <ul className="plain-list" aria-label="Productos del plan">
        {form.products.map((p) => (
          <li key={p.id}>
            {p.name} <span className="muted small">{p.sku}</span>{" "}
            <button type="button" className="link" onClick={() => setForm({ ...form, products: form.products.filter((x) => x.id !== p.id) })}>Quitar</button>
          </li>
        ))}
      </ul>
      <ProductSearch products={products} onPick={(p) => !form.products.some((x) => x.id === p.id)
        && setForm({ ...form, products: [...form.products, { id: p.id, sku: p.sku, name: p.name }] })} />
      <label className="check">
        <input type="checkbox" checked={form.isActive} onChange={(e) => setForm({ ...form, isActive: e.target.checked })} /> Activo
      </label>
      {problem && <p className="muted small">{problem}</p>}
      {error && <p className="error" role="alert">{error}</p>}
      <div className="row">
        <button type="button" onClick={onCancel}>Cerrar</button>
        <button type="button" className="primary" disabled={busy || !!problem} onClick={submit}>{plan ? "Guardar plan" : "Crear plan"}</button>
      </div>
    </div>
  );
}
