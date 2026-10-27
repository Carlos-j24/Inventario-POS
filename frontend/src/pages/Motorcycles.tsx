import { useCallback, useEffect, useState, type FormEvent } from "react";

import { api, type Customer, type Motorcycle, type MotorcycleDetail } from "../api";
import CustomerPicker from "../components/CustomerPicker";
import {
  BRANDS, describeMotorcycle, emptyForm, formatKm, formOf, formProblem, mileageNeedsNote, payload, type MotorcycleForm,
} from "../motorcycle";

const URL = "/api/workshop/motorcycles/";
/** Cierra con punto, sin repetirlo si el nombre ya termina en uno ("… S.A.S."). */
const sentence = (text: string) => (text.endsWith(".") ? text : `${text}.`);
const date = (iso: string) => new Date(iso).toLocaleDateString("es-CO", { day: "numeric", month: "short", year: "numeric" });

/** Spec 009, T3: recepción del taller busca, registra y lleva las motos con sus dueños. */
export default function Motorcycles() {
  const [q, setQ] = useState("");
  const [inactive, setInactive] = useState(false);
  const [rows, setRows] = useState<Motorcycle[] | null>(null);
  const [selected, setSelected] = useState<number | "new" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    const params = new URLSearchParams();
    if (q.trim()) params.set("q", q.trim());
    if (inactive) params.set("inactive", "1");
    return api<Motorcycle[]>(`${URL}?${params}`).then((r) => { setRows(r); setError(null); }).catch((e: Error) => setError(e.message));
  }, [q, inactive]);

  useEffect(() => {
    const timer = setTimeout(load, 250);
    return () => clearTimeout(timer);
  }, [load]);

  return (
    <div className="two-cols">
      <section className="card">
        <div className="row spread">
          <h2>Motos</h2>
          <button className="primary" onClick={() => setSelected("new")}>Nueva moto</button>
        </div>
        <div className="row filters">
          <input
            placeholder="Placa, chasis, cédula, teléfono o nombre"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            aria-label="Buscar moto"
            autoFocus
          />
          <label className="check">
            <input type="checkbox" checked={inactive} onChange={(e) => setInactive(e.target.checked)} /> Mostrar inactivas
          </label>
        </div>
        {error && <p className="error" role="alert">{error}</p>}
        <table className="cart sales-list">
          <thead><tr><th>Placa</th><th>Moto</th><th>Dueño</th><th className="num">Km</th></tr></thead>
          <tbody>
            {(rows ?? []).map((m) => (
              <tr key={m.id} className={m.id === selected ? "selected" : !m.is_active ? "voided" : ""} onClick={() => setSelected(m.id)}>
                <td><button className="link" onClick={() => setSelected(m.id)}>{m.plate || "Sin placa"}</button></td>
                <td>{[m.brand, m.model].filter(Boolean).join(" ")}</td>
                <td>{m.owner.name} <span className="muted small">{m.owner.phone}</span></td>
                <td className="num">{m.mileage.toLocaleString("es-CO")}</td>
              </tr>
            ))}
            {rows && rows.length === 0 && (
              <tr><td colSpan={4} className="muted center">{q.trim() ? "Ninguna moto coincide." : "Todavía no hay motos registradas."}</td></tr>
            )}
          </tbody>
        </table>
      </section>
      <aside className="card">
        {selected === "new" && (
          <NewMotorcycle onCreated={(m) => { load(); setSelected(m.id); }} onCancel={() => setSelected(null)} />
        )}
        {typeof selected === "number" && <MotorcycleCard key={selected} id={selected} onChanged={load} />}
        {selected === null && <p className="muted">Busca una moto o registra una nueva.</p>}
      </aside>
    </div>
  );
}

function Fields({ form, onChange }: { form: MotorcycleForm; onChange: (f: MotorcycleForm) => void }) {
  const set = (k: keyof MotorcycleForm) => (e: { target: { value: string } }) => onChange({ ...form, [k]: e.target.value });
  return (
    <>
      <div className="row">
        <label>Placa<input value={form.plate} onChange={set("plate")} placeholder="ABC12D" /></label>
        <label>Chasis (si no tiene placa)<input value={form.vin} onChange={set("vin")} /></label>
      </div>
      <div className="row">
        <label>Marca<input value={form.brand} onChange={set("brand")} list="motorcycle-brands" /></label>
        <label>Modelo<input value={form.model} onChange={set("model")} placeholder="Boxer CT 100" /></label>
      </div>
      <datalist id="motorcycle-brands">{BRANDS.map((b) => <option key={b} value={b} />)}</datalist>
      <div className="row">
        <label>Año<input inputMode="numeric" value={form.year} onChange={set("year")} /></label>
        <label>Cilindraje (cc)<input inputMode="numeric" value={form.displacement_cc} onChange={set("displacement_cc")} /></label>
        <label>Color<input value={form.color} onChange={set("color")} /></label>
      </div>
      <label>Notas<textarea value={form.notes} onChange={set("notes")} rows={2} /></label>
    </>
  );
}

function NewMotorcycle({ onCreated, onCancel }: { onCreated: (m: Motorcycle) => void; onCancel: () => void }) {
  const [owner, setOwner] = useState<Customer | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [mileage, setMileage] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const problem = formProblem(form) ?? (mileage.trim() && !/^\d+$/.test(mileage.trim()) ? "El kilometraje va en números." : null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!owner || problem) return;
    setBusy(true);
    setError(null);
    try {
      onCreated(await api<Motorcycle>(URL, {
        method: "POST", body: { ...payload(form), owner: owner.id, mileage: Number(mileage.trim() || 0) },
      }));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="action-form" onSubmit={submit}>
      <h2>Nueva moto</h2>
      <CustomerPicker value={owner} onChange={setOwner} emptyLabel="Sin dueño" requirePhone />
      <Fields form={form} onChange={setForm} />
      <label>Kilometraje<input inputMode="numeric" value={mileage} onChange={(e) => setMileage(e.target.value)} placeholder="0" /></label>
      {!owner && <p className="muted small">Elige o registra al dueño.</p>}
      {owner && problem && <p className="muted small">{problem}</p>}
      {error && <p className="error" role="alert">{error}</p>}
      <div className="row">
        <button type="button" onClick={onCancel}>Cancelar</button>
        <button className="primary" disabled={busy || !owner || !!problem}>Registrar moto</button>
      </div>
    </form>
  );
}

function MotorcycleCard({ id, onChanged }: { id: number; onChanged: () => void }) {
  const [moto, setMoto] = useState<MotorcycleDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    api<MotorcycleDetail>(`${URL}${id}/`).then(setMoto).catch((e: Error) => setError(e.message));
  }, [id]);

  /** Envía un cambio; si sale bien, muestra la ficha nueva. Dice si salió bien. */
  async function send(path: string, method: string, body: unknown, done: string): Promise<boolean> {
    setError(null);
    setMessage(null);
    try {
      setMoto(await api<MotorcycleDetail>(`${URL}${id}/${path}`, { method, body }));
      setMessage(done);
      onChanged();
      return true;
    } catch (err) {
      setError((err as Error).message);
      return false;
    }
  }

  if (!moto) return error ? <p className="error" role="alert">{error}</p> : <p className="muted">Cargando…</p>;
  const previous = moto.ownerships.filter((o) => o.ended_at);

  return (
    <div className="action-form">
      <h2>{describeMotorcycle(moto)}</h2>
      {!moto.is_active && <span className="badge danger">Inactiva</span>}
      <p>
        Dueño: <strong>{moto.owner.name}</strong> · {moto.owner.phone}
        <span className="muted small"> · {moto.owner.id_number}</span>
      </p>
      {message && <p className="change" role="status">{message}</p>}
      {error && <p className="error" role="alert">{error}</p>}

      <h3>Kilometraje</h3>
      <MileageForm key={moto.mileage} current={moto.mileage} onSave={(body) => send("mileage/", "POST", body, "Kilometraje guardado.")} />
      <p className="muted small">
        {moto.mileage_at ? `${formatKm(moto.mileage)} el ${date(moto.mileage_at)}` : "Sin lecturas todavía."}
      </p>
      {moto.mileage_readings.length > 0 && (
        <ul className="plain-list small" aria-label="Lecturas de kilometraje">
          {moto.mileage_readings.map((r, i) => (
            <li key={i}>
              {date(r.recorded_at)}: {formatKm(r.mileage)} <span className="muted">({r.recorded_by})</span>
              {r.note && <> · <em>{r.note}</em></>}
            </li>
          ))}
        </ul>
      )}

      <h3>Dueño</h3>
      <OwnerChange current={moto.owner.id} onSave={(owner) => send("owner/", "POST", { owner: owner.id }, sentence(`Ahora es de ${owner.name}`))} />
      {previous.length > 0 && (
        <ul className="plain-list small" aria-label="Dueños anteriores">
          {previous.map((o, i) => (
            <li key={i}>{o.customer.name} · del {date(o.started_at)} al {date(o.ended_at!)}</li>
          ))}
        </ul>
      )}

      <h3>Datos de la moto</h3>
      <EditData key={moto.updated_at} moto={moto} onSave={(body, done) => send("", "PATCH", body, done)} />
    </div>
  );
}

function MileageForm({ current, onSave }: { current: number; onSave: (body: { mileage: number; note: string }) => Promise<boolean> }) {
  const [value, setValue] = useState("");
  const [note, setNote] = useState("");
  const next = Number(value);
  const valid = /^\d+$/.test(value.trim());
  const lower = valid && mileageNeedsNote(current, next);

  return (
    <div className="action-form">
      <div className="row">
        <input inputMode="numeric" value={value} onChange={(e) => setValue(e.target.value)} placeholder={`Va en ${formatKm(current)}`} aria-label="Kilometraje nuevo" />
        <button disabled={!valid || (lower && !note.trim())} onClick={() => onSave({ mileage: next, note: note.trim() })}>Guardar kilometraje</button>
      </div>
      {lower && (
        <>
          <p className="muted small">El kilometraje solo sube: si cambiaron el tablero o hubo un error, explícalo.</p>
          <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Por qué baja" aria-label="Nota del kilometraje" />
        </>
      )}
    </div>
  );
}

function OwnerChange({ current, onSave }: { current: number; onSave: (owner: Customer) => Promise<boolean> }) {
  const [owner, setOwner] = useState<Customer | null>(null);
  return (
    <div className="action-form">
      <CustomerPicker value={owner} onChange={setOwner} emptyLabel="Elegir nuevo dueño" requirePhone />
      {owner && (
        <button disabled={owner.id === current} onClick={() => onSave(owner).then((ok) => ok && setOwner(null))}>
          {owner.id === current ? "Ya es el dueño" : `Pasar la moto a ${owner.name}`}
        </button>
      )}
    </div>
  );
}

function EditData({ moto, onSave }: { moto: Motorcycle; onSave: (body: Record<string, unknown>, done: string) => Promise<boolean> }) {
  const [form, setForm] = useState(() => formOf(moto));
  const problem = formProblem(form);
  const changed = JSON.stringify(payload(form)) !== JSON.stringify(payload(formOf(moto)));

  return (
    <div className="action-form">
      <Fields form={form} onChange={setForm} />
      {changed && problem && <p className="muted small">{problem}</p>}
      <div className="row">
        <button disabled={!changed || !!problem} onClick={() => onSave(payload(form), "Datos guardados.")}>Guardar datos</button>
        {moto.is_active ? (
          <button className="danger-btn" onClick={() => onSave({ is_active: false }, "Moto desactivada: ya no sale en la búsqueda.")}>Desactivar moto</button>
        ) : (
          <button onClick={() => onSave({ is_active: true }, "Moto reactivada.")}>Reactivar moto</button>
        )}
      </div>
    </div>
  );
}
