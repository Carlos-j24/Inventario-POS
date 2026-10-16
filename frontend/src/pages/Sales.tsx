import { useCallback, useEffect, useState, type FormEvent } from "react";

import { api, type PaymentMethod, type Register, type SaleDetail, type SaleListItem } from "../api";
import { formatMoney, formatQty, toCents } from "../money";

const METHOD_LABEL: Record<PaymentMethod, string> = { CASH: "Efectivo", CARD: "Tarjeta", TRANSFER: "Transferencia" };

/** Fecha de hoy en la hora del equipo (AAAA-MM-DD), para el filtro de fecha. */
export function todayIso(now = new Date()): string {
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 10);
}

/** Arma la consulta de la lista: el número busca en cualquier fecha y manda sobre los demás filtros de fecha. */
export function salesQuery(f: { number: string; date: string; register: string; status: string; review: boolean }): string {
  const q = new URLSearchParams();
  if (f.number.trim()) q.set("number", f.number.trim());
  else if (f.date && f.date !== todayIso()) q.set("date", f.date); // sin fecha, el servidor usa hoy
  if (f.register) q.set("register", f.register);
  if (f.status) q.set("status", f.status);
  if (f.review) q.set("needs_review", "1");
  const s = q.toString();
  return `/api/sales/${s ? `?${s}` : ""}`;
}

const time = (iso: string) => new Date(iso).toLocaleTimeString("es-CO", { hour: "2-digit", minute: "2-digit" });

/** Spec 003: el supervisor busca una venta y ve su detalle (anular y devolver llegan en la T4). */
export default function Sales() {
  const [number, setNumber] = useState("");
  const [date, setDate] = useState(todayIso);
  const [register, setRegister] = useState("");
  const [status, setStatus] = useState("");
  const [review, setReview] = useState(false);
  const [registers, setRegisters] = useState<Register[]>([]);
  const [sales, setSales] = useState<SaleListItem[] | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (query: string) => {
    setError(null);
    try {
      setSales(await api<SaleListItem[]>(query));
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    // Las cajas sirven para filtrar; quien solo tiene reportes puede no verlas, y no pasa nada.
    api<Register[]>("/api/cash/registers/").then(setRegisters).catch(() => setRegisters([]));
  }, []);

  useEffect(() => {
    load(salesQuery({ number: "", date, register, status, review }));
  }, [load, date, register, status, review]);

  function search(e: FormEvent) {
    e.preventDefault();
    load(salesQuery({ number, date, register, status, review }));
  }

  const total = (sales ?? []).filter((s) => s.status === "COMPLETED").reduce((sum, s) => sum + toCents(s.total), 0);

  return (
    <div className="two-cols sales-page">
      <section className="card">
        <h2>Ventas</h2>
        <form className="row filters" onSubmit={search}>
          <input
            placeholder="Número: V-000123"
            value={number}
            onChange={(e) => setNumber(e.target.value)}
            aria-label="Buscar por número"
          />
          <button>Buscar</button>
          <input type="date" value={date} onChange={(e) => { setNumber(""); setDate(e.target.value); }} aria-label="Fecha" />
          {registers.length > 0 && (
            <select value={register} onChange={(e) => setRegister(e.target.value)} aria-label="Caja">
              <option value="">Todas las cajas</option>
              {registers.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
            </select>
          )}
          <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Estado">
            <option value="">Todas</option>
            <option value="COMPLETED">Completadas</option>
            <option value="VOIDED">Anuladas</option>
          </select>
          <label className="check">
            <input type="checkbox" checked={review} onChange={(e) => setReview(e.target.checked)} /> Para revisión
          </label>
        </form>
        {error && <p className="error" role="alert">{error}</p>}
        {sales && (
          <>
            <p className="muted small">
              {sales.length} venta(s) · total completadas {formatMoney(total)}
              {sales.length === 200 && " · se muestran las 200 más recientes"}
            </p>
            <table className="cart sales-list">
              <thead>
                <tr><th>Número</th><th>Hora</th><th>Caja</th><th>Vendió / cobró</th><th className="num">Total</th><th /></tr>
              </thead>
              <tbody>
                {sales.map((s) => (
                  <tr
                    key={s.id}
                    className={s.id === selected ? "selected" : s.status === "VOIDED" ? "voided" : ""}
                    onClick={() => setSelected(s.id)}
                  >
                    <td><button className="link" onClick={() => setSelected(s.id)}>{s.number}</button></td>
                    <td>{time(s.occurred_at)}</td>
                    <td>{s.register}</td>
                    <td>{s.salesperson === s.seller ? s.seller : `${s.salesperson} / ${s.seller}`}</td>
                    <td className="num">{formatMoney(toCents(s.total))}</td>
                    <td><SaleBadges sale={s} /></td>
                  </tr>
                ))}
                {sales.length === 0 && <tr><td colSpan={6} className="muted center">No hay ventas con estos filtros.</td></tr>}
              </tbody>
            </table>
          </>
        )}
      </section>
      <aside className="card">
        {selected ? <SaleDetailView id={selected} /> : <p className="muted">Elige una venta para ver su detalle.</p>}
      </aside>
    </div>
  );
}

function SaleBadges({ sale }: { sale: Pick<SaleListItem, "status" | "needs_review" | "offline" | "order_code"> }) {
  return (
    <span className="row badges">
      {sale.status === "VOIDED" && <span className="badge danger">Anulada</span>}
      {sale.needs_review && <span className="badge warn">Revisión</span>}
      {sale.offline && <span className="badge">Sin conexión</span>}
      {sale.order_code && <span className="badge">Pedido {sale.order_code}</span>}
    </span>
  );
}

export function SaleDetailView({ id }: { id: number }) {
  const [sale, setSale] = useState<SaleDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setSale(null);
    setError(null);
    api<SaleDetail>(`/api/sales/${id}/`).then(setSale).catch((e) => setError(e.message));
  }, [id]);

  if (error) return <p className="error">{error}</p>;
  if (!sale) return <p className="muted">Cargando…</p>;

  const returned = sale.returns.reduce((sum, r) => sum + toCents(r.total), 0);
  return (
    <div className="sale-detail">
      <div className="row spread">
        <h2>{sale.number}</h2>
        <SaleBadges sale={sale} />
      </div>
      <p className="muted">
        {new Date(sale.occurred_at).toLocaleString("es-CO")} · {sale.register} · turno{" "}
        {sale.shift_open ? "abierto" : "cerrado"}
      </p>
      <p>
        Vendió <strong>{sale.salesperson}</strong> · cobró <strong>{sale.seller}</strong>
        {sale.order_code && <> · pedido <strong className="code-chip">{sale.order_code}</strong></>}
      </p>
      {sale.status === "VOIDED" && <p className="error">Anulada: {sale.void_reason}</p>}

      <table className="cart">
        <thead><tr><th>Producto</th><th className="num">Cant.</th><th className="num">Precio</th><th className="num">Total</th></tr></thead>
        <tbody>
          {sale.lines.map((l) => (
            <tr key={l.id}>
              <td>
                {l.name}
                {Number(l.returned_quantity) > 0 && (
                  <div className="muted small">devuelto {formatQty(l.returned_quantity)} {l.unit}</div>
                )}
              </td>
              <td className="num">{formatQty(l.quantity)} {l.unit}</td>
              <td className="num">
                {formatMoney(toCents(l.unit_price))}
                {l.unit_price !== l.catalog_price && (
                  <div className="muted small">catálogo {formatMoney(toCents(l.catalog_price))}</div>
                )}
              </td>
              <td className="num">{formatMoney(toCents(l.total))}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <table className="plain">
        <tbody>
          <tr><td>Subtotal</td><td className="num">{formatMoney(toCents(sale.subtotal))}</td></tr>
          <tr><td>IVA</td><td className="num">{formatMoney(toCents(sale.tax))}</td></tr>
          <tr><td><strong>Total</strong></td><td className="num"><strong>{formatMoney(toCents(sale.total))}</strong></td></tr>
          {returned > 0 && <tr><td>Devuelto</td><td className="num">−{formatMoney(returned)}</td></tr>}
        </tbody>
      </table>

      <h3>Pagos</h3>
      <ul className="plain-list">
        {sale.payments.map((p, i) => (
          <li key={i}>
            {METHOD_LABEL[p.method]} {formatMoney(toCents(p.amount))}
            {toCents(p.change) > 0 && <span className="muted"> (recibió {formatMoney(toCents(p.received))}, vueltas {formatMoney(toCents(p.change))})</span>}
            {p.reference && <span className="muted"> · {p.reference}</span>}
          </li>
        ))}
      </ul>

      {sale.returns.length > 0 && (
        <>
          <h3>Devoluciones</h3>
          <ul className="plain-list">
            {sale.returns.map((r) => (
              <li key={r.id}>
                {r.number} · {formatMoney(toCents(r.total))} en {METHOD_LABEL[r.refund_method].toLowerCase()} · {r.reason}
                <span className="muted"> ({r.user}, {new Date(r.created_at).toLocaleString("es-CO")})</span>
              </li>
            ))}
          </ul>
        </>
      )}
      {sale.needs_review && (
        <p className="muted small">
          {sale.reviewed_at ? `Revisada: ${sale.review_note || "sin nota"}` : "Pendiente de revisión en la bandeja."}
        </p>
      )}
    </div>
  );
}
