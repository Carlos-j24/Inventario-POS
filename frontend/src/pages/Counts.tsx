import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { flushSync } from "react-dom";

import { api, type Category, type CountLine, type CountStatus, type PhysicalCount, type Warehouse } from "../api";
import { useCan } from "../auth";
import { filterLines, findLine, parseCount } from "../counting";
import { formatMoney, formatQty, toCents } from "../money";

const URL = "/api/inventory/counts/";
const FILTERS: { id: "" | CountStatus; label: string }[] = [
  { id: "OPEN", label: "Abiertos" },
  { id: "SUBMITTED", label: "Por aprobar" },
  { id: "APPROVED", label: "Aprobados" },
  { id: "VOIDED", label: "Anulados" },
  { id: "", label: "Todos" },
];
const when = (iso: string) => new Date(iso).toLocaleString("es-CO", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

/** Spec 006, T6: conteo físico ciego; quien tiene inventory.adjust aprueba las diferencias. */
export default function Counts() {
  const [filter, setFilter] = useState<"" | CountStatus>("OPEN");
  const [rows, setRows] = useState<PhysicalCount[] | null>(null);
  const [selected, setSelected] = useState<number | "new" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api<PhysicalCount[]>(`${URL}${filter ? `?status=${filter}` : ""}`).then(setRows).catch((e: Error) => setError(e.message));
  }, [filter]);
  useEffect(load, [load]);

  return (
    <div className="two-cols sales-page">
      <section className="card">
        <div className="row spread">
          <h2>Conteos físicos</h2>
          <button className="primary" onClick={() => setSelected("new")}>Nuevo conteo</button>
        </div>
        <div className="row filters">
          {FILTERS.map((f) => (
            <button key={f.id} className={f.id === filter ? "tab active" : "tab"} aria-pressed={f.id === filter} onClick={() => setFilter(f.id)}>
              {f.label}
            </button>
          ))}
        </div>
        {error && <p className="error" role="alert">{error}</p>}
        <div className="table-wrap">
          <table className="cart sales-list" aria-label="Conteos">
            <thead><tr><th>Número</th><th>Qué se cuenta</th><th className="num">Avance</th><th>Abierto</th><th /></tr></thead>
            <tbody>
              {(rows ?? []).map((c) => (
                <tr key={c.id} className={c.id === selected ? "selected" : ""} onClick={() => setSelected(c.id)}>
                  <td><button className="link" onClick={() => setSelected(c.id)}>{c.number}</button></td>
                  <td>{c.warehouse}{c.category ? ` · ${c.category}` : " · toda la bodega"}</td>
                  <td className="num">{c.counted} / {c.total}</td>
                  <td>{when(c.created_at)} <span className="muted small">{c.opened_by}</span></td>
                  <td><StatusBadge status={c.status} /></td>
                </tr>
              ))}
              {rows && rows.length === 0 && <tr><td colSpan={5} className="muted center">Nada por aquí.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
      <aside className="card">
        {selected === "new" && <NewCount onOpened={(c) => { setFilter("OPEN"); load(); setSelected(c.id); }} onCancel={() => setSelected(null)} />}
        {typeof selected === "number" && <CountView key={selected} id={selected} onChanged={load} />}
        {selected === null && <p className="muted">Elige un conteo o abre uno nuevo.</p>}
      </aside>
    </div>
  );
}

function StatusBadge({ status }: { status: CountStatus }) {
  if (status === "OPEN") return <span className="badge warn">Abierto</span>;
  if (status === "SUBMITTED") return <span className="badge warn">Por aprobar</span>;
  if (status === "VOIDED") return <span className="badge danger">Anulado</span>;
  return <span className="badge">Aprobado</span>;
}

function NewCount({ onOpened, onCancel }: { onOpened: (c: PhysicalCount) => void; onCancel: () => void }) {
  const [warehouses, setWarehouses] = useState<Warehouse[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [warehouse, setWarehouse] = useState<number | null>(null);
  const [category, setCategory] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [clientUuid] = useState(() => crypto.randomUUID());

  useEffect(() => {
    api<Warehouse[]>("/api/inventory/warehouses/").then((ws) => { setWarehouses(ws); setWarehouse(ws[0]?.id ?? null); }).catch((e: Error) => setError(e.message));
    api<Category[]>("/api/catalog/categories/").then(setCategories).catch(() => setCategories([]));
  }, []);

  async function open(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      onOpened(await api<PhysicalCount>(URL, { method: "POST", body: { client_uuid: clientUuid, warehouse, category: category ? Number(category) : null } }));
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <form className="action-form" onSubmit={open} aria-label="Nuevo conteo">
      <h2>Nuevo conteo</h2>
      <label>
        Bodega
        <select value={warehouse ?? ""} onChange={(e) => setWarehouse(Number(e.target.value))}>
          {warehouses.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
        </select>
      </label>
      <label>
        Qué contar
        <select value={category} onChange={(e) => setCategory(e.target.value)}>
          <option value="">Toda la bodega</option>
          {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
      </label>
      <p className="muted small">Cuenta y guarda estante por estante: la caja puede seguir vendiendo mientras tanto.</p>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="row">
        <button type="button" onClick={onCancel}>Cancelar</button>
        <button className="primary" disabled={!warehouse}>Abrir conteo</button>
      </div>
    </form>
  );
}

function CountView({ id, onChanged }: { id: number; onChanged: () => void }) {
  const [count, setCount] = useState<PhysicalCount | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    api<PhysicalCount>(`${URL}${id}/`).then(setCount).catch((e: Error) => setError(e.message));
  }, [id]);
  useEffect(reload, [reload]);

  async function post(action: string, body: Record<string, unknown> = {}) {
    setError(null);
    try {
      setCount(await api<PhysicalCount>(`${URL}${id}/${action}/`, { method: "POST", body }));
      onChanged();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  /** Línea guardada: se cambia en el detalle y se refresca el avance de la lista. */
  function saved(line: CountLine) {
    if (!count) return;
    const wasPending = count.lines!.find((l) => l.id === line.id)?.counted === null;
    setCount({ ...count, counted: count.counted + (wasPending ? 1 : 0), lines: count.lines!.map((l) => (l.id === line.id ? line : l)) });
    onChanged();
  }

  if (!count) return error ?<p className="error" role="alert">{error}</p> : <p className="muted">Cargando…</p>;
  return (
    <div className="action-form">
      <h2>{count.number}</h2>
      <p className="muted">
        {count.warehouse}{count.category ? ` · ${count.category}` : " · toda la bodega"} · abrió {count.opened_by} el {when(count.created_at)} · {count.counted} de {count.total} contados
      </p>
      <p><StatusBadge status={count.status} />{count.decided_by && <span className="muted small"> {count.decided_by} el {when(count.decided_at!)}</span>}</p>
      {count.status === "OPEN" && <Counting count={count} onSaved={saved} onSubmit={() => post("submit")} />}
      {count.status === "SUBMITTED" && <Review count={count} onApprove={(zero) => post("approve", { zero_uncounted: zero })} />}
      {count.status === "APPROVED" && <Summary count={count} />}
      {count.status === "VOIDED" && <p className="error">Anulado: {count.void_note}</p>}
      {(count.status === "OPEN" || count.status === "SUBMITTED") && <VoidCount onVoid={(note) => post("void", { note })} />}
      {error && <p className="error" role="alert">{error}</p>}
    </div>
  );
}

function Counting({ count, onSaved, onSubmit }: { count: PhysicalCount; onSaved: (line: CountLine) => void; onSubmit: () => void }) {
  const lines = count.lines ?? [];
  const [scan, setScan] = useState("");
  const [text, setText] = useState("");
  const [onlyPending, setOnlyPending] = useState(false);
  const [drafts, setDrafts] = useState<Record<number, { qty: string; unit: string }>>({});
  const [notice, setNotice] = useState<string | null>(null);
  const inputs = useRef<Record<number, HTMLInputElement | null>>({});

  const draft = (l: CountLine) => drafts[l.id] ?? { qty: "", unit: l.base_unit };
  const setDraft = (l: CountLine, change: Partial<{ qty: string; unit: string }>) => setDrafts({ ...drafts, [l.id]: { ...draft(l), ...change } });

  function onScan(e: FormEvent) {
    e.preventDefault();
    const hit = findLine(lines, scan);
    if (!hit) return setNotice(`"${scan}" no está en este conteo.`);
    // flushSync: la fila ya está en pantalla (aunque el filtro la ocultara) y el foco pasa
    // a la cantidad antes de la siguiente tecla, por rápido que se escriba después del lector.
    flushSync(() => {
      setNotice(null);
      setScan("");
      setText("");
      setDraft(hit.line, { unit: hit.unit });
    });
    inputs.current[hit.line.id]?.focus();
  }

  async function save(l: CountLine) {
    const d = draft(l);
    const quantity = parseCount(d.qty);
    if (quantity === null) return setNotice(`${l.sku}: escribe cuánto hay (0 si no hay).`);
    try {
      onSaved(await api<CountLine>(`${URL}${count.id}/lines/${l.id}/`, { method: "PATCH", body: { quantity, unit: d.unit } }));
      setDrafts({ ...drafts, [l.id]: { qty: "", unit: d.unit } });
      setNotice(null);
    } catch (err) {
      setNotice((err as Error).message);
    }
  }

  return (
    <section aria-label="Contar">
      <form onSubmit={onScan}>
        <input className="search" value={scan} onChange={(e) => setScan(e.target.value)} placeholder="Escanea el código o escribe el SKU y Enter" aria-label="Escanear producto" autoFocus />
      </form>
      <div className="row filters">
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Filtrar por nombre o SKU" aria-label="Filtrar productos" />
        <label className="check"><input type="checkbox" checked={onlyPending} onChange={(e) => setOnlyPending(e.target.checked)} /> Solo sin contar</label>
      </div>
      {notice && <p className="error" role="alert">{notice}</p>}
      <div className="table-wrap">
        <table className="cart" aria-label="Productos a contar">
          <thead><tr><th>Producto</th><th className="num">Contado</th><th>Cuánto hay</th><th /></tr></thead>
          <tbody>
            {filterLines(lines, text, onlyPending).map((l) => (
              <tr key={l.id}>
                <td><span className="muted small">{l.sku}</span> {l.name}</td>
                <td className="num">{l.counted === null ? "—" : `${formatQty(l.counted)} ${l.base_unit}`}</td>
                <td>
                  <span className="row">
                    <input className="qty" ref={(el) => { inputs.current[l.id] = el; }} value={draft(l).qty} inputMode="decimal"
                      onChange={(e) => setDraft(l, { qty: e.target.value })} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); save(l); } }}
                      aria-label={`Cantidad de ${l.name}`} />
                    {l.units.length > 0 && (
                      <select value={draft(l).unit} onChange={(e) => setDraft(l, { unit: e.target.value })} aria-label={`Unidad de ${l.name}`}>
                        {[l.base_unit, ...l.units.map((u) => u.unit)].map((u) => <option key={u} value={u}>{u}</option>)}
                      </select>
                    )}
                  </span>
                </td>
                <td><button className="link" onClick={() => save(l)} disabled={!draft(l).qty.trim()}>Guardar</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <button className="primary" onClick={onSubmit} disabled={count.counted === 0}>Terminar y enviar a aprobación</button>
    </section>
  );
}

function Review({ count, onApprove }: { count: PhysicalCount; onApprove: (zero: "all" | number[]) => void }) {
  const can = useCan();
  const lines = count.lines ?? [];
  const pending = lines.filter((l) => l.counted === null);
  const [zero, setZero] = useState<number[]>([]);
  if (!can("inventory.adjust")) {
    return <p className="muted">Enviado: lo aprueba quien tiene permiso de ajustes (jefe de bodega).</p>;
  }
  const allZero = pending.length > 0 && zero.length === pending.length;
  return (
    <section aria-label="Aprobar conteo">
      <DifferencesTable lines={lines.filter((l) => l.counted !== null)} />
      {pending.length > 0 && (
        <>
          <h3>Sin contar ({pending.length})</h3>
          <p className="muted small">No se ajustan, salvo que los marques en 0 (por ejemplo, si de verdad no hay).</p>
          <label className="check"><input type="checkbox" checked={allZero} onChange={(e) => setZero(e.target.checked ? pending.map((l) => l.id) : [])} /> Marcar todos en 0</label>
          <ul className="plain-list">
            {pending.map((l) => (
              <li key={l.id}>
                <label className="check">
                  <input type="checkbox" checked={zero.includes(l.id)} onChange={(e) => setZero(e.target.checked ? [...zero, l.id] : zero.filter((x) => x !== l.id))} aria-label={`Marcar ${l.name} en 0`} />
                  <span className="muted small">{l.sku}</span> {l.name}
                </label>
              </li>
            ))}
          </ul>
        </>
      )}
      <button className="primary" onClick={() => onApprove(allZero ? "all" : zero)}>Aprobar y ajustar diferencias</button>
    </section>
  );
}

function DifferencesTable({ lines }: { lines: CountLine[] }) {
  const showValue = lines.some((l) => l.value !== null);
  const total = lines.reduce((sum, l) => sum + toCents(l.value ?? "0"), 0);
  return (
    <div className="table-wrap">
      <table className="cart" aria-label="Diferencias">
        <thead><tr><th>Producto</th><th className="num">Contado</th><th className="num">Sistema</th><th className="num">Diferencia</th>{showValue && <th className="num">Valor</th>}</tr></thead>
        <tbody>
          {lines.map((l) => {
            const diff = Number(l.difference ?? 0);
            return (
              <tr key={l.id}>
                <td><span className="muted small">{l.sku}</span> {l.name}{l.marked_zero && <span className="badge"> marcado en 0</span>}</td>
                <td className="num">{formatQty(l.counted ?? "0")}</td>
                <td className="num">{l.expected === null ? "—" : formatQty(l.expected)}</td>
                <td className="num"><span className={diff < 0 ? "error" : diff > 0 ? "change" : undefined}>{diff > 0 ? "+" : ""}{formatQty(String(diff))} {l.base_unit}</span></td>
                {showValue && <td className="num">{formatMoney(toCents(l.value ?? "0"))}</td>}
              </tr>
            );
          })}
          {showValue && <tr><td colSpan={4}><strong>Total</strong></td><td className="num"><strong>{formatMoney(total)}</strong></td></tr>}
        </tbody>
      </table>
    </div>
  );
}

function Summary({ count }: { count: PhysicalCount }) {
  const lines = (count.lines ?? []).filter((l) => l.counted !== null);
  const changed = lines.filter((l) => l.difference !== null && Number(l.difference) !== 0);
  return (
    <section aria-label="Resultado">
      <p>{count.adjustment ? `Las diferencias se aplicaron con el ajuste ${count.adjustment}.` : "Sin diferencias: no hizo falta ajustar."}</p>
      {lines[0]?.expected !== null && lines.length > 0 && <DifferencesTable lines={changed.length ? changed : lines} />}
    </section>
  );
}

function VoidCount({ onVoid }: { onVoid: (note: string) => void }) {
  const can = useCan();
  const [note, setNote] = useState("");
  if (!can("inventory.adjust")) return null;
  return (
    <div className="row sale-actions">
      <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Por qué se anula" aria-label="Motivo de la anulación" />
      <button className="danger-btn" onClick={() => onVoid(note)} disabled={!note.trim()}>Anular conteo</button>
    </div>
  );
}
