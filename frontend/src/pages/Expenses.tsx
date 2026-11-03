import { useCallback, useEffect, useState, type FormEvent } from "react";

import { api, type Expense, type ExpenseCategory, type ExpenseList, type Register } from "../api";
import {
  changedExpense, emptyExpense, expenseProblem, lockedReason, monthStart, newExpensePayload, toExpenseForm, type ExpenseForm,
} from "../expense";
import { formatMoney, toCents } from "../money";
import { todayIso } from "./Sales";

const URL = "/api/expenses/";
const money = (value: string) => formatMoney(toCents(value));
const day = (iso: string) => new Date(`${iso}T12:00:00`).toLocaleDateString("es-CO", { day: "numeric", month: "short", year: "numeric" });
const when = (iso: string) => new Date(iso).toLocaleString("es-CO", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });

/** Spec 013, T5: el administrador anota los gastos del negocio para sacar la ganancia real. */
export default function Expenses() {
  const today = todayIso();
  const [period, setPeriod] = useState({ from: monthStart(today), to: today });
  const [list, setList] = useState<ExpenseList | null>(null);
  const [categories, setCategories] = useState<ExpenseCategory[]>([]);
  const [selected, setSelected] = useState<number | "new" | "categories" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api<ExpenseList>(`${URL}?${new URLSearchParams(period)}`).then((r) => { setList(r); setError(null); }).catch((e: Error) => setError(e.message));
  }, [period]);
  const loadCategories = useCallback(() => {
    api<ExpenseCategory[]>(`${URL}categories/`).then(setCategories).catch((e: Error) => setError(e.message));
  }, []);
  useEffect(load, [load]);
  useEffect(loadCategories, [loadCategories]);

  return (
    <div className="two-cols">
      <section className="card">
        <div className="row spread">
          <h2>Gastos</h2>
          <span className="row">
            <button onClick={() => setSelected("categories")}>Categorías</button>
            <button className="primary" onClick={() => setSelected("new")}>Anotar gasto</button>
          </span>
        </div>
        <div className="row filters">
          <input type="date" aria-label="Desde" value={period.from} max={today} onChange={(e) => e.target.value && setPeriod({ ...period, from: e.target.value })} />
          <input type="date" aria-label="Hasta" value={period.to} max={today} onChange={(e) => e.target.value && setPeriod({ ...period, to: e.target.value })} />
        </div>
        {error && <p className="error" role="alert">{error}</p>}
        <table className="cart sales-list" aria-label="Gastos del periodo">
          <thead><tr><th>Fecha</th><th>Categoría</th><th>Nota</th><th className="num">Valor</th><th /></tr></thead>
          <tbody>
            {(list?.expenses ?? []).map((e) => (
              <tr key={e.id} className={e.id === selected ? "selected" : e.status === "VOIDED" ? "voided" : ""} onClick={() => setSelected(e.id)}>
                <td><button className="link" onClick={() => setSelected(e.id)}>{day(e.spent_on)}</button></td>
                <td>{e.category_name}</td>
                <td>{e.note}{e.register && <span className="muted small"> · de {e.register.name}</span>}</td>
                <td className="num">{money(e.amount)}</td>
                <td>{e.status === "VOIDED" && <span className="badge danger">Anulado</span>}</td>
              </tr>
            ))}
            {list && list.expenses.length === 0 && <tr><td colSpan={5} className="muted center">Sin gastos en el periodo.</td></tr>}
          </tbody>
          {list && (
            <tfoot><tr><td colSpan={3}>Total (sin anulados)</td><td className="num">{money(list.total)}</td><td /></tr></tfoot>
          )}
        </table>
      </section>
      <aside className="card">
        {selected === "new" && (
          <NewExpense today={today} categories={categories} onSaved={(e) => { load(); setSelected(e.id); }} onCancel={() => setSelected(null)} />
        )}
        {selected === "categories" && <Categories categories={categories} onChanged={loadCategories} />}
        {typeof selected === "number" && (
          <ExpenseCard key={selected} id={selected} today={today} categories={categories} onChanged={load} />
        )}
        {selected === null && <p className="muted">Elige un gasto o anota uno nuevo.</p>}
      </aside>
    </div>
  );
}

function CategorySelect({ categories, value, onChange }: { categories: ExpenseCategory[]; value: string; onChange: (v: string) => void }) {
  // Una categoría desactivada solo aparece si el gasto ya la tiene.
  const shown = categories.filter((c) => c.is_active || String(c.id) === value);
  return (
    <label>
      Categoría
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">Elige…</option>
        {shown.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
      </select>
    </label>
  );
}

function NewExpense({ today, categories, onSaved, onCancel }: {
  today: string; categories: ExpenseCategory[]; onSaved: (e: Expense) => void; onCancel: () => void;
}) {
  const [form, setForm] = useState<ExpenseForm>(emptyExpense(today));
  const [registers, setRegisters] = useState<Register[]>([]);
  const [fromTill, setFromTill] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { api<Register[]>("/api/cash/registers/").then(setRegisters).catch(() => setRegisters([])); }, []);
  const open = registers.filter((r) => r.open_shift != null);
  const set = <K extends keyof ExpenseForm>(key: K, value: ExpenseForm[K]) => setForm({ ...form, [key]: value });
  const problem = expenseProblem(form, today) ?? (fromTill && !form.register ? "Elige la caja de la que salió." : null);

  async function save(e: FormEvent) {
    e.preventDefault();
    if (problem) return;
    setBusy(true);
    setError(null);
    try {
      onSaved(await api<Expense>(URL, { method: "POST", body: newExpensePayload(form) }));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="action-form" aria-label="Anotar gasto" onSubmit={save}>
      <h2>Anotar gasto</h2>
      <div className="row">
        <label>Fecha<input type="date" value={form.spent_on} max={today} onChange={(e) => set("spent_on", e.target.value)} /></label>
        <label>Valor<input inputMode="numeric" value={form.amount} onChange={(e) => set("amount", e.target.value)} placeholder="15000" /></label>
      </div>
      <CategorySelect categories={categories} value={form.category} onChange={(v) => set("category", v)} />
      <label>Nota<input value={form.note} maxLength={200} onChange={(e) => set("note", e.target.value)} placeholder="Jabón para el lavadero" /></label>
      <label className="check">
        <input type="checkbox" checked={fromTill} disabled={!open.length}
          onChange={(e) => { setFromTill(e.target.checked); setForm({ ...form, register: e.target.checked && open.length === 1 ? String(open[0].id) : "", spent_on: e.target.checked ? today : form.spent_on }); }} />
        Pagado de la caja (sale del arqueo del turno)
      </label>
      {!open.length && <p className="muted small">Ninguna caja tiene el turno abierto.</p>}
      {fromTill && open.length > 1 && (
        <label>
          Caja
          <select value={form.register} onChange={(e) => set("register", e.target.value)}>
            <option value="">Elige…</option>
            {open.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
          </select>
        </label>
      )}
      {problem && form.amount && <p className="muted small">{problem}</p>}
      {error && <p className="error" role="alert">{error}</p>}
      <div className="row">
        <button type="button" onClick={onCancel}>Cancelar</button>
        <button className="primary" disabled={busy || !!problem}>Anotar</button>
      </div>
    </form>
  );
}

function ExpenseCard({ id, today, categories, onChanged }: { id: number; today: string; categories: ExpenseCategory[]; onChanged: () => void }) {
  const [expense, setExpense] = useState<Expense | null>(null);
  const [form, setForm] = useState<ExpenseForm | null>(null);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const show = (e: Expense) => { setExpense(e); setForm(toExpenseForm(e)); };
  useEffect(() => { api<Expense>(`${URL}${id}/`).then(show).catch((e: Error) => setError(e.message)); }, [id]);

  async function send(path: string, method: string, body: unknown, done: string) {
    setError(null);
    setMessage(null);
    try {
      show(await api<Expense>(`${URL}${id}/${path}`, { method, body }));
      setMessage(done);
      onChanged();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  if (!expense || !form) return error ? <p className="error" role="alert">{error}</p> : <p className="muted">Cargando…</p>;
  const locked = lockedReason(expense);
  const voided = expense.status === "VOIDED";
  const fromClosedTill = !!expense.register && !expense.register.shift_open;
  const changes = changedExpense(form, expense);
  const problem = expenseProblem({ ...form, register: "" }, today);
  const set = <K extends keyof ExpenseForm>(key: K, value: ExpenseForm[K]) => setForm({ ...form, [key]: value });

  return (
    <div className="action-form">
      <div className="row spread">
        <h2>{expense.category_name} · {money(expense.amount)}</h2>
        {voided && <span className="badge danger">Anulado</span>}
      </div>
      <p className="muted">
        {day(expense.spent_on)} · anotó {expense.created_by}
        {expense.register && ` · pagado de ${expense.register.name}`}
      </p>
      {voided && <p className="error">Anulado: {expense.void_reason}</p>}
      {locked && !voided && <p className="muted small">{locked}</p>}
      {message && <p className="change" role="status">{message}</p>}
      {error && <p className="error" role="alert">{error}</p>}

      {!voided && (
        <form aria-label="Corregir gasto" onSubmit={(e) => { e.preventDefault(); send("", "PATCH", changes, "Gasto corregido."); }}>
          <div className="row">
            <label>Fecha<input type="date" value={form.spent_on} max={today} disabled={!!expense.register} onChange={(e) => set("spent_on", e.target.value)} /></label>
            <label>Valor<input inputMode="numeric" value={form.amount} disabled={fromClosedTill} onChange={(e) => set("amount", e.target.value)} /></label>
          </div>
          <CategorySelect categories={categories} value={form.category} onChange={(v) => set("category", v)} />
          <label>Nota<input value={form.note} maxLength={200} onChange={(e) => set("note", e.target.value)} /></label>
          {problem && <p className="muted small">{problem}</p>}
          <button disabled={!Object.keys(changes).length || !!problem}>Guardar corrección</button>
        </form>
      )}

      {!locked && (
        <div className="row">
          <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Motivo" aria-label="Motivo de la anulación" />
          <button className="danger-btn" disabled={!reason.trim()} onClick={() => send("void/", "POST", { reason: reason.trim() }, "Gasto anulado.")}>
            Anular gasto
          </button>
        </div>
      )}

      <h3>Historia</h3>
      <ul className="plain-list small" aria-label="Historia del gasto">
        {expense.events.map((e, i) => (
          <li key={i}>{when(e.at)}: {e.label} <span className="muted">({e.user})</span>{e.detail && <> · <em>{e.detail}</em></>}</li>
        ))}
      </ul>
    </div>
  );
}

function Categories({ categories, onChanged }: { categories: ExpenseCategory[]; onChanged: () => void }) {
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function send(url: string, method: string, body: unknown) {
    setError(null);
    try {
      await api(url, { method, body });
      onChanged();
      return true;
    } catch (err) {
      setError((err as Error).message);
      return false;
    }
  }

  return (
    <div className="action-form">
      <h2>Categorías de gasto</h2>
      <p className="muted small">Una categoría con gastos no se borra: se desactiva y deja de ofrecerse.</p>
      {error && <p className="error" role="alert">{error}</p>}
      <ul className="plain-list" aria-label="Categorías">
        {categories.map((c) => (
          <li key={c.id} className="row spread">
            <span className={c.is_active ? "" : "muted"}>{c.name}{!c.is_active && " (desactivada)"}</span>
            <button className="link" onClick={() => send(`${URL}categories/${c.id}/`, "PATCH", { is_active: !c.is_active })}>
              {c.is_active ? "Desactivar" : "Activar"}
            </button>
          </li>
        ))}
      </ul>
      <form className="row" onSubmit={async (e) => { e.preventDefault(); if (await send(`${URL}categories/`, "POST", { name: name.trim() })) setName(""); }}>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Nueva categoría" aria-label="Nueva categoría" maxLength={60} />
        <button disabled={!name.trim()}>Agregar</button>
      </form>
    </div>
  );
}
