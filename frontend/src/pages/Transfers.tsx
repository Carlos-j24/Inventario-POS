import { useCallback, useEffect, useState } from "react";

import { api, type Product, type Transfer, type Warehouse } from "../api";
import { fetchWithCache } from "../cache";
import ProductSearch from "../components/ProductSearch";
import { formatMoney, formatQty, toCents } from "../money";
import { newTransferLine, transferBody, type TransferDraftLine } from "../transfer";

const URL = "/api/inventory/transfers/";
const when = (iso: string) => new Date(iso).toLocaleString("es-CO", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

/** Spec 006, T7: pasar mercancía entre bodegas en un solo paso (sale y entra a la vez). */
export default function Transfers() {
  const [rows, setRows] = useState<Transfer[] | null>(null);
  const [selected, setSelected] = useState<number | "new" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api<Transfer[]>(URL).then(setRows).catch((e: Error) => setError(e.message));
  }, []);
  useEffect(load, [load]);

  const current = typeof selected === "number" ? rows?.find((t) => t.id === selected) : undefined;

  return (
    <div className="two-cols sales-page">
      <section className="card">
        <div className="row spread">
          <h2>Traslados</h2>
          <button className="primary" onClick={() => setSelected("new")}>Nuevo traslado</button>
        </div>
        {error && <p className="error" role="alert">{error}</p>}
        <div className="table-wrap">
          <table className="cart sales-list" aria-label="Traslados">
            <thead><tr><th>Número</th><th>De → a</th><th>Hizo</th><th>Fecha</th></tr></thead>
            <tbody>
              {(rows ?? []).map((t) => (
                <tr key={t.id} className={t.id === selected ? "selected" : ""} onClick={() => setSelected(t.id)}>
                  <td><button className="link" onClick={() => setSelected(t.id)}>{t.number}</button></td>
                  <td>{t.origin} → {t.destination} <span className="muted small">{t.lines.length} producto(s)</span></td>
                  <td>{t.created_by}</td>
                  <td>{when(t.created_at)}</td>
                </tr>
              ))}
              {rows && rows.length === 0 && <tr><td colSpan={4} className="muted center">Nada por aquí.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
      <aside className="card">
        {selected === "new" && <NewTransfer onCreated={(t) => { load(); setSelected(t.id); }} onCancel={() => setSelected(null)} />}
        {current && <TransferDetail transfer={current} />}
        {selected === null && <p className="muted">Elige un traslado o haz uno nuevo.</p>}
      </aside>
    </div>
  );
}

function NewTransfer({ onCreated, onCancel }: { onCreated: (t: Transfer) => void; onCancel: () => void }) {
  const [warehouses, setWarehouses] = useState<Warehouse[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [origin, setOrigin] = useState<number | null>(null);
  const [destination, setDestination] = useState<number | null>(null);
  const [note, setNote] = useState("");
  const [lines, setLines] = useState<TransferDraftLine[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Un UUID por traslado: un doble clic o un reintento no lo duplica.
  const [clientUuid] = useState(() => crypto.randomUUID());

  useEffect(() => {
    api<Warehouse[]>("/api/inventory/warehouses/")
      .then((ws) => { setWarehouses(ws); setOrigin(ws[0]?.id ?? null); setDestination(ws[1]?.id ?? null); })
      .catch((e: Error) => setError(e.message));
    fetchWithCache<Product[]>("/api/catalog/products/").then((r) => setProducts(r.data)).catch((e: Error) => setError(e.message));
  }, []);

  const update = (key: string, change: Partial<TransferDraftLine>) => setLines(lines.map((l) => (l.key === key ? { ...l, ...change } : l)));

  async function submit() {
    const result = transferBody({ clientUuid, origin, destination, note, lines });
    if ("error" in result) return setError(result.error);
    setBusy(true);
    setError(null);
    try {
      onCreated(await api<Transfer>(URL, { method: "POST", body: result.body }));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    // Un contenedor y no un <form>: el buscador de productos trae su propio formulario (Enter del lector).
    <div className="action-form" role="form" aria-label="Nuevo traslado">
      <h2>Nuevo traslado</h2>
      {warehouses.length === 1 && <p className="muted small">Solo hay una bodega activa: crea otra en el administrador para poder trasladar.</p>}
      <div className="row">
        <label>
          Sale de
          <select value={origin ?? ""} onChange={(e) => setOrigin(Number(e.target.value))}>
            {warehouses.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
          </select>
        </label>
        <label>
          Entra a
          <select value={destination ?? ""} onChange={(e) => setDestination(Number(e.target.value))}>
            <option value="" disabled>Elige…</option>
            {warehouses.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
          </select>
        </label>
      </div>
      <label>Nota (opcional)<input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Para qué: surtir la vitrina…" /></label>
      <ProductSearch products={products} onPick={(p, unit) => setLines([...lines, newTransferLine(p, unit)])} />
      {lines.length > 0 && (
        <table className="cart" aria-label="Productos del traslado">
          <thead><tr><th>Producto</th><th>Cantidad</th><th>Unidad</th><th /></tr></thead>
          <tbody>
            {lines.map((l) => (
              <tr key={l.key}>
                <td>{l.product.name}</td>
                <td><input className="qty" value={l.quantity} onChange={(e) => update(l.key, { quantity: e.target.value })} aria-label={`Cantidad de ${l.product.name}`} inputMode="decimal" /></td>
                <td>
                  <select value={l.unit} onChange={(e) => update(l.key, { unit: e.target.value })} aria-label={`Unidad de ${l.product.name}`}>
                    {[l.product.base_unit, ...l.product.units.map((u) => u.unit)].map((u) => <option key={u} value={u}>{u}</option>)}
                  </select>
                </td>
                <td><button type="button" className="link" onClick={() => setLines(lines.filter((x) => x.key !== l.key))} aria-label={`Quitar ${l.product.name}`}>Quitar</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="muted small">Sale y entra de una vez, al costo promedio de la bodega de origen. Si te equivocas, haz otro traslado al revés.</p>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="row">
        <button type="button" onClick={onCancel}>Cancelar</button>
        <button type="button" className="primary" onClick={submit} disabled={busy}>{busy ? "Trasladando…" : "Trasladar"}</button>
      </div>
    </div>
  );
}

function TransferDetail({ transfer: t }: { transfer: Transfer }) {
  const showValue = t.lines.some((l) => l.value !== null);
  const total = t.lines.reduce((sum, l) => sum + toCents(l.value ?? "0"), 0);
  return (
    <div className="action-form">
      <h2>{t.number}</h2>
      <p className="muted">De {t.origin} a {t.destination} · {t.created_by} el {when(t.created_at)}</p>
      {t.note && <p>{t.note}</p>}
      <table className="cart" aria-label="Líneas">
        <thead><tr><th>Producto</th><th className="num">Cantidad</th>{showValue && <th className="num">Valor</th>}</tr></thead>
        <tbody>
          {t.lines.map((l) => (
            <tr key={l.id}>
              <td><span className="muted small">{l.sku}</span> {l.name}</td>
              <td className="num">
                {formatQty(l.quantity)} {l.unit}
                {l.unit !== l.base_unit && <div className="muted small">{formatQty(l.base_quantity)} {l.base_unit}</div>}
              </td>
              {showValue && <td className="num">{formatMoney(toCents(l.value ?? "0"))}</td>}
            </tr>
          ))}
          {showValue && <tr><td><strong>Total</strong></td><td /><td className="num"><strong>{formatMoney(total)}</strong></td></tr>}
        </tbody>
      </table>
    </div>
  );
}
