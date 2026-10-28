import { useCallback, useEffect, useState } from "react";

import { api, type Adjustment, type AdjustmentStatus, type Product } from "../api";
import { adjustmentBody, directionFor, newLine, REASONS, type DraftLine } from "../adjustment";
import { useCan } from "../auth";
import { fetchWithCache } from "../cache";
import { stockedProducts } from "../cart";
import ProductSearch from "../components/ProductSearch";
import { formatMoney, formatQty, toCents } from "../money";
import { useWarehouseChoice } from "../useWarehouseChoice";

const URL = "/api/inventory/adjustments/";
const FILTERS: { id: "" | AdjustmentStatus; label: string }[] = [
  { id: "PENDING", label: "Pendientes" },
  { id: "APPROVED", label: "Aprobados" },
  { id: "REJECTED", label: "Rechazados" },
  { id: "", label: "Todos" },
];
const when = (iso: string) => new Date(iso).toLocaleString("es-CO", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

/** Spec 006, T4: bodega reporta bajas y sobrantes; quien tiene inventory.adjust los aprueba. */
export default function Adjustments() {
  const [filter, setFilter] = useState<"" | AdjustmentStatus>("PENDING");
  const [rows, setRows] = useState<Adjustment[] | null>(null);
  const [selected, setSelected] = useState<number | "new" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api<Adjustment[]>(`${URL}${filter ? `?status=${filter}` : ""}`).then(setRows).catch((e: Error) => setError(e.message));
  }, [filter]);
  useEffect(load, [load]);

  const current = typeof selected === "number" ? rows?.find((a) => a.id === selected) : undefined;

  return (
    <div className="two-cols sales-page">
      <section className="card">
        <div className="row spread">
          <h2>Ajustes de inventario</h2>
          <button className="primary" onClick={() => setSelected("new")}>Nuevo ajuste</button>
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
          <table className="cart sales-list" aria-label="Ajustes">
            <thead><tr><th>Número</th><th>Motivo</th><th>Pidió</th><th>Fecha</th><th /></tr></thead>
            <tbody>
              {(rows ?? []).map((a) => (
                <tr key={a.id} className={a.id === selected ? "selected" : ""} onClick={() => setSelected(a.id)}>
                  <td><button className="link" onClick={() => setSelected(a.id)}>{a.number}</button></td>
                  <td>{a.reason_label} <span className="muted small">{a.lines.length} producto(s)</span></td>
                  <td>{a.requested_by}</td>
                  <td>{when(a.created_at)}</td>
                  <td><StatusBadge status={a.status} /></td>
                </tr>
              ))}
              {rows && rows.length === 0 && <tr><td colSpan={5} className="muted center">Nada por aquí.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
      <aside className="card">
        {selected === "new" && (
          <NewAdjustment
            onCreated={(a) => { setFilter("PENDING"); load(); setSelected(a.id); }}
            onCancel={() => setSelected(null)}
          />
        )}
        {current && <AdjustmentDetail key={current.id} adjustment={current} onChanged={load} />}
        {selected === null && <p className="muted">Elige un ajuste o crea uno nuevo.</p>}
      </aside>
    </div>
  );
}

function StatusBadge({ status }: { status: AdjustmentStatus }) {
  if (status === "PENDING") return <span className="badge warn">Pendiente</span>;
  if (status === "REJECTED") return <span className="badge danger">Rechazado</span>;
  return <span className="badge">Aprobado</span>;
}

function NewAdjustment({ onCreated, onCancel }: { onCreated: (a: Adjustment) => void; onCancel: () => void }) {
  const [products, setProducts] = useState<Product[]>([]);
  const [reason, setReason] = useState("DAMAGE");
  const [note, setNote] = useState("");
  const [lines, setLines] = useState<DraftLine[]>([]);
  const [error, setError] = useState<string | null>(null);
  const { warehouses, warehouse, choose } = useWarehouseChoice(setError);
  const [busy, setBusy] = useState(false);
  // Un UUID por ajuste: un doble clic o un reintento no lo duplica.
  const [clientUuid] = useState(() => crypto.randomUUID());
  const bothWays = REASONS.find((r) => r.id === reason)?.direction === "BOTH";

  useEffect(() => {
    fetchWithCache<Product[]>("/api/catalog/products/").then((r) => setProducts(stockedProducts(r.data))).catch((e: Error) => setError(e.message));
  }, []);

  const update = (key: string, change: Partial<DraftLine>) => setLines(lines.map((l) => (l.key === key ? { ...l, ...change } : l)));

  async function submit() {
    const result = adjustmentBody({ clientUuid, warehouse, reason, note, lines });
    if ("error" in result) return setError(result.error);
    setBusy(true);
    setError(null);
    try {
      onCreated(await api<Adjustment>(URL, { method: "POST", body: result.body }));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    // Un contenedor y no un <form>: el buscador de productos trae su propio formulario (Enter del lector).
    <div className="action-form" role="form" aria-label="Nuevo ajuste">
      <h2>Nuevo ajuste</h2>
      <div className="row">
        <label>
          Bodega
          <select value={warehouse ?? ""} onChange={(e) => choose(Number(e.target.value))}>
            {warehouses.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
          </select>
        </label>
        <label>
          Motivo
          <select value={reason} onChange={(e) => setReason(e.target.value)}>
            {REASONS.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
          </select>
        </label>
      </div>
      <label>Nota<textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="Qué pasó: se cayó del estante, se usó en el mostrador…" rows={2} /></label>
      <ProductSearch products={products} onPick={(p, unit) => setLines([...lines, newLine(p, unit, reason)])} />
      {lines.length > 0 && (
        <table className="cart" aria-label="Productos del ajuste">
          <thead><tr><th>Producto</th><th>Cantidad</th><th>Unidad</th>{bothWays && <th>Sentido</th>}<th /></tr></thead>
          <tbody>
            {lines.map((l) => {
              const direction = directionFor(reason, l.direction);
              return (
                <tr key={l.key}>
                  <td>{l.product.name}{direction === "IN" && (
                    <input className="qty" value={l.cost} onChange={(e) => update(l.key, { cost: e.target.value })}
                      placeholder="Costo (si no tiene)" aria-label={`Costo de ${l.product.name}`} inputMode="decimal" />
                  )}</td>
                  <td><input className="qty" value={l.quantity} onChange={(e) => update(l.key, { quantity: e.target.value })} aria-label={`Cantidad de ${l.product.name}`} inputMode="decimal" /></td>
                  <td>
                    <select value={l.unit} onChange={(e) => update(l.key, { unit: e.target.value })} aria-label={`Unidad de ${l.product.name}`}>
                      {[l.product.base_unit, ...l.product.units.map((u) => u.unit)].map((u) => <option key={u} value={u}>{u}</option>)}
                    </select>
                  </td>
                  {bothWays && (
                    <td>
                      <select value={l.direction} onChange={(e) => update(l.key, { direction: e.target.value as DraftLine["direction"] })} aria-label={`Sentido de ${l.product.name}`}>
                        <option value="OUT">Sale</option>
                        <option value="IN">Entra</option>
                      </select>
                    </td>
                  )}
                  <td><button type="button" className="link" onClick={() => setLines(lines.filter((x) => x.key !== l.key))} aria-label={`Quitar ${l.product.name}`}>Quitar</button></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      <p className="muted small">
        {bothWays ? "Error de registro: cada producto puede entrar o salir." : directionFor(reason, "OUT") === "IN" ? "Sobrante: la mercancía entra al costo promedio; si el producto no tiene costo, escríbelo." : "Baja: la mercancía sale al costo promedio. Queda pendiente hasta que la apruebe el jefe de bodega."}
      </p>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="row">
        <button type="button" onClick={onCancel}>Cancelar</button>
        <button type="button" className="primary" onClick={submit} disabled={busy}>{busy ? "Enviando…" : "Enviar para aprobación"}</button>
      </div>
    </div>
  );
}

function AdjustmentDetail({ adjustment: a, onChanged }: { adjustment: Adjustment; onChanged: () => void }) {
  const can = useCan();
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const showValue = a.lines.some((l) => l.value !== null);
  const total = a.lines.reduce((sum, l) => sum + toCents(l.value ?? "0"), 0);

  async function act(action: "approve" | "reject") {
    setBusy(true);
    setError(null);
    try {
      await api(`${URL}${a.id}/${action}/`, { method: "POST", body: action === "reject" ? { note } : {} });
      onChanged();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="action-form">
      <h2>{a.number}</h2>
      <p className="muted">{a.reason_label} · bodega {a.warehouse} · pidió {a.requested_by} el {when(a.created_at)}</p>
      <p><StatusBadge status={a.status} />{a.decided_by && <span className="muted small"> {a.status === "APPROVED" ? "aprobó" : "rechazó"} {a.decided_by} el {when(a.decided_at!)}</span>}</p>
      <p>{a.note}</p>
      {a.rejection_note && <p className="error">Rechazado: {a.rejection_note}</p>}
      <table className="cart" aria-label="Líneas">
        <thead><tr><th>Producto</th><th className="num">Cantidad</th>{showValue && <th className="num">Valor</th>}</tr></thead>
        <tbody>
          {a.lines.map((l) => (
            <tr key={l.id}>
              <td><span className="muted small">{l.sku}</span> {l.name}</td>
              <td className="num">
                {Number(l.base_quantity) < 0 ? "−" : "+"}{formatQty(l.quantity)} {l.unit}
                {l.unit !== l.base_unit && <div className="muted small">{formatQty(String(Math.abs(Number(l.base_quantity))))} {l.base_unit}</div>}
              </td>
              {showValue && <td className="num">{formatMoney(toCents(l.value ?? "0"))}</td>}
            </tr>
          ))}
          {showValue && <tr><td><strong>Total</strong></td><td /><td className="num"><strong>{formatMoney(total)}</strong></td></tr>}
        </tbody>
      </table>
      {a.status === "PENDING" && can("inventory.adjust") && (
        <div className="sale-actions">
          <button className="primary" onClick={() => act("approve")} disabled={busy}>Aprobar y aplicar</button>
          <div className="row">
            <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Por qué se rechaza" aria-label="Motivo del rechazo" />
            <button className="danger-btn" onClick={() => act("reject")} disabled={busy || !note.trim()}>Rechazar</button>
          </div>
        </div>
      )}
      {a.status === "PENDING" && !can("inventory.adjust") && <p className="muted small">Lo aprueba quien tiene permiso de ajustes (jefe de bodega).</p>}
      {error && <p className="error" role="alert">{error}</p>}
    </div>
  );
}
