import { useCallback, useEffect, useState } from "react";

import { api, type Customer, type Order, type Product, type QuoteDetail, type QuoteRow, type QuoteStatus } from "../api";
import { useCan } from "../auth";
import { addToCart, cartTotalCents, type CartLine } from "../cart";
import CartTable from "../components/CartTable";
import CustomerPicker from "../components/CustomerPicker";
import ProductSearch from "../components/ProductSearch";
import { formatMoney, formatQty, toCents } from "../money";
import { convertBody, defaultPicks, DEFAULT_VALID_DAYS, MAX_VALID_DAYS, plainQuantity, quoteBody } from "../quote";

const URL = "/api/quotes/";
const FILTERS: { id: "" | QuoteStatus; label: string }[] = [
  { id: "VALID", label: "Vigentes" },
  { id: "EXPIRED", label: "Vencidas" },
  { id: "CONVERTED", label: "Convertidas" },
  { id: "VOIDED", label: "Anuladas" },
  { id: "", label: "Todas" },
];
const ORDER_STATUS: Record<Order["status"], string> = { PENDING: "por cobrar", PAID: "cobrado", CANCELLED: "cancelado", EXPIRED: "vencido" };
const day = (iso: string) => new Date(`${iso}T12:00:00`).toLocaleDateString("es-CO", { day: "numeric", month: "short", year: "numeric" });

/** Spec 007, T4: el vendedor cotiza, y cuando el cliente vuelve la convierte en pedido para la caja. */
export default function Quotes() {
  const can = useCan();
  const [filter, setFilter] = useState<"" | QuoteStatus>("VALID");
  const [text, setText] = useState("");
  const [query, setQuery] = useState("");
  const [rows, setRows] = useState<QuoteRow[] | null>(null);
  const [selected, setSelected] = useState<number | "new" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    const params = new URLSearchParams({ status: filter });
    if (query) params.set("q", query);
    api<QuoteRow[]>(`${URL}?${params}`).then(setRows).catch((e: Error) => setError(e.message));
  }, [filter, query]);
  useEffect(load, [load]);

  return (
    <div className="two-cols sales-page">
      <section className="card">
        <div className="row spread">
          <h2>Cotizaciones</h2>
          {can("sales.create") && <button className="primary" onClick={() => setSelected("new")}>Nueva cotización</button>}
        </div>
        <form className="row" onSubmit={(e) => { e.preventDefault(); setQuery(text.trim()); }}>
          <input className="search" value={text} onChange={(e) => setText(e.target.value)} placeholder="Número (COT-45), cliente o teléfono" aria-label="Buscar cotización" />
          <button>Buscar</button>
        </form>
        <div className="row filters">
          {FILTERS.map((f) => (
            <button key={f.id} className={f.id === filter ? "tab active" : "tab"} aria-pressed={f.id === filter} onClick={() => setFilter(f.id)}>
              {f.label}
            </button>
          ))}
        </div>
        {error && <p className="error" role="alert">{error}</p>}
        <div className="table-wrap">
          <table className="cart sales-list" aria-label="Cotizaciones">
            <thead><tr><th>Número</th><th>Cliente</th><th className="num">Total</th><th>Vigente hasta</th><th /></tr></thead>
            <tbody>
              {(rows ?? []).map((q) => (
                <tr key={q.id} className={q.id === selected ? "selected" : ""} onClick={() => setSelected(q.id)}>
                  <td><button className="link" onClick={() => setSelected(q.id)}>{q.number}</button></td>
                  <td>{q.customer}{q.customer_phone && <span className="muted small"> · {q.customer_phone}</span>} <span className="muted small">({q.created_by})</span></td>
                  <td className="num">{formatMoney(toCents(q.total))}</td>
                  <td>{day(q.valid_until)}</td>
                  <td><StatusBadge status={q.status} label={q.status_label} /></td>
                </tr>
              ))}
              {rows && rows.length === 0 && <tr><td colSpan={5} className="muted center">Nada por aquí.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
      <aside className="card">
        {selected === "new" && <NewQuote onCreated={(q) => { setFilter("VALID"); setQuery(""); setText(""); load(); setSelected(q.id); }} onCancel={() => setSelected(null)} />}
        {typeof selected === "number" && <QuoteView key={selected} id={selected} onChanged={load} onOpen={setSelected} />}
        {selected === null && <p className="muted">Elige una cotización o haz una nueva. El cliente que vuelve con el número la encuentra aunque la haya hecho otro vendedor.</p>}
      </aside>
    </div>
  );
}

function StatusBadge({ status, label }: { status: QuoteStatus; label: string }) {
  const tone = status === "VALID" ? "badge warn" : status === "CONVERTED" ? "badge" : "badge danger";
  return <span className={tone}>{label}</span>;
}

function NewQuote({ onCreated, onCancel }: { onCreated: (q: QuoteDetail) => void; onCancel: () => void }) {
  const [products, setProducts] = useState<Product[]>([]);
  const [lines, setLines] = useState<CartLine[]>([]);
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [customerName, setCustomerName] = useState("");
  const [customerPhone, setCustomerPhone] = useState("");
  const [note, setNote] = useState("");
  const [validDays, setValidDays] = useState(String(DEFAULT_VALID_DAYS));
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Un UUID por cotización: un doble clic o un reintento no la duplica.
  const [clientUuid] = useState(() => crypto.randomUUID());

  useEffect(() => {
    api<Product[]>("/api/catalog/products/").then(setProducts).catch((e: Error) => setError(e.message));
  }, []);

  async function save() {
    const result = quoteBody({ clientUuid, customer, customerName, customerPhone, note, validDays, lines });
    if ("error" in result) return setError(result.error);
    setBusy(true);
    setError(null);
    try {
      onCreated(await api<QuoteDetail>(URL, { method: "POST", body: result.body }));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    // Un contenedor y no un <form>: el buscador de productos trae su propio formulario (Enter del lector).
    <div className="action-form" role="form" aria-label="Nueva cotización">
      <h2>Nueva cotización</h2>
      <div className="row">
        <label>A nombre de<input value={customerName} onChange={(e) => setCustomerName(e.target.value)} placeholder="Don Jorge (maestro de obra)" /></label>
        <label>Teléfono<input value={customerPhone} onChange={(e) => setCustomerPhone(e.target.value)} inputMode="tel" placeholder="Opcional" /></label>
      </div>
      <CustomerPicker value={customer} onChange={setCustomer} emptyLabel="ninguno registrado (opcional)" />
      <ProductSearch products={products} onPick={(p, u) => setLines((ls) => addToCart(ls, p, u))} />
      <CartTable lines={lines} onChange={setLines} emptyText="Busca o escanea los productos de la lista del cliente." />
      <div className="row">
        <label>Vigencia (días)<input className="qty" value={validDays} onChange={(e) => setValidDays(e.target.value)} inputMode="numeric" /></label>
        <label>Nota<input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Entrega en obra, calle 12…" /></label>
      </div>
      <p className="muted small">Precios de hoy, con IVA. Vigencia de 1 a {MAX_VALID_DAYS} días: mientras esté vigente se cobra al precio cotizado.</p>
      <div className="total-label">Total</div>
      <div className="total">{formatMoney(cartTotalCents(lines))}</div>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="row">
        <button type="button" onClick={onCancel}>Cancelar</button>
        <button type="button" className="primary" onClick={save} disabled={busy}>{busy ? "Guardando…" : "Guardar cotización"}</button>
      </div>
    </div>
  );
}

function QuoteView({ id, onChanged, onOpen }: { id: number; onChanged: () => void; onOpen: (id: number) => void }) {
  const can = useCan();
  const [quote, setQuote] = useState<QuoteDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [order, setOrder] = useState<Order | null>(null);

  const reload = useCallback(() => {
    api<QuoteDetail>(`${URL}${id}/`).then(setQuote).catch((e: Error) => setError(e.message));
  }, [id]);
  useEffect(reload, [reload]);

  async function duplicate() {
    setError(null);
    try {
      const copy = await api<QuoteDetail>(`${URL}${id}/duplicate/`, { method: "POST", body: { client_uuid: crypto.randomUUID() } });
      onChanged();
      onOpen(copy.id);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  if (!quote) return error ? <p className="error" role="alert">{error}</p> : <p className="muted">Cargando…</p>;
  return (
    <div className="action-form">
      <h2>{quote.number}</h2>
      <p className="muted">
        {quote.customer}{quote.customer_document && ` · ${quote.customer_document}`}{quote.customer_phone && ` · ${quote.customer_phone}`}
        {" · "}la hizo {quote.created_by} · vigente hasta el {day(quote.valid_until)}
      </p>
      <p><StatusBadge status={quote.status} label={quote.status_label} />{quote.duplicated_from && <span className="muted small"> duplicada de {quote.duplicated_from}</span>}</p>
      {quote.note && <p>{quote.note}</p>}
      {quote.status === "VOIDED" && <p className="error">Anulada por {quote.voided_by}: {quote.void_note}</p>}
      {quote.status === "EXPIRED" && <p className="warn-note">Vencida: ya no se cobra al precio cotizado. Duplícala para cotizar con los precios de hoy.</p>}

      {order ? (
        <OrderCreated order={order} onDone={() => { setOrder(null); reload(); onChanged(); }} />
      ) : quote.can_convert && can("sales.create") ? (
        // La key reinicia lo precargado cuando cambia lo que queda (al volver de un pedido llega el detalle nuevo).
        <Convert key={quote.lines.map((l) => l.remaining).join()} quote={quote} onConverted={(o) => { setOrder(o); onChanged(); }} />
      ) : (
        <LinesTable quote={quote} />
      )}

      {quote.orders.length > 0 && (
        <>
          <h3>Pedidos de esta cotización</h3>
          <ul className="plain-list" aria-label="Pedidos de esta cotización">
            {quote.orders.map((o) => (
              <li key={o.id}>
                <strong className="code-chip">{o.code}</strong> {formatMoney(toCents(o.total))} · {ORDER_STATUS[o.status]}
                {o.sale_number && <span className="muted small"> ({o.sale_number})</span>}
              </li>
            ))}
          </ul>
        </>
      )}

      {can("sales.create") && <button type="button" onClick={duplicate}>Duplicar con los precios de hoy</button>}
      {quote.status === "VALID" && <VoidQuote id={quote.id} onVoided={() => { reload(); onChanged(); }} />}
      {error && <p className="error" role="alert">{error}</p>}
    </div>
  );
}

function LinesTable({ quote }: { quote: QuoteDetail }) {
  return (
    <table className="cart" aria-label="Líneas de la cotización">
      <thead><tr><th>Producto</th><th className="num">Cotizado</th><th className="num">Cobrado</th><th className="num">Total</th></tr></thead>
      <tbody>
        {quote.lines.map((l) => (
          <tr key={l.id}>
            <td><span className="muted small">{l.sku}</span> {l.name} <span className="muted small">· {formatMoney(toCents(l.unit_price))}/{l.unit}</span></td>
            <td className="num">{formatQty(l.quantity)} {l.unit}</td>
            <td className="num">{formatQty(l.charged)}</td>
            <td className="num">{formatMoney(toCents(l.total))}</td>
          </tr>
        ))}
        <tr><td colSpan={3}><strong>Total</strong></td><td className="num"><strong>{formatMoney(toCents(quote.total))}</strong></td></tr>
      </tbody>
    </table>
  );
}

function Convert({ quote, onConverted }: { quote: QuoteDetail; onConverted: (order: Order) => void }) {
  const [picks, setPicks] = useState(() => defaultPicks(quote.lines));
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Un UUID por conversión: un reintento no crea dos pedidos.
  const [clientUuid] = useState(() => crypto.randomUUID());
  const left = quote.lines.some((l) => Number(l.remaining) > 0);

  async function convert() {
    const result = convertBody(clientUuid, quote.lines, picks);
    if ("error" in result) return setError(result.error);
    setBusy(true);
    setError(null);
    try {
      onConverted(await api<Order>(`${URL}${quote.id}/order/`, { method: "POST", body: result.body }));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-label="Convertir en pedido">
      <table className="cart" aria-label="Líneas de la cotización">
        <thead><tr><th>Producto</th><th className="num">Cotizado</th><th className="num">En pedidos</th><th className="num">Cobrado</th><th>Se lleva</th></tr></thead>
        <tbody>
          {quote.lines.map((l) => (
            <tr key={l.id}>
              <td>
                <span className="muted small">{l.sku}</span> {l.name} <span className="muted small">· {formatMoney(toCents(l.unit_price))}/{l.unit}</span>
                {!l.active && <div className="error small">Ya no está a la venta.</div>}
              </td>
              <td className="num">{formatQty(l.quantity)} {l.unit}</td>
              <td className="num">{formatQty(l.in_orders)}</td>
              <td className="num">{formatQty(l.charged)}</td>
              <td>
                <input className="qty" value={picks[l.id]} onChange={(e) => setPicks({ ...picks, [l.id]: e.target.value })}
                  disabled={!l.active || Number(l.remaining) === 0} inputMode="decimal" aria-label={`Cuánto se lleva de ${l.name}`} />
                <span className="muted small"> de {plainQuantity(l.remaining)}</span>
              </td>
            </tr>
          ))}
          <tr><td colSpan={4}><strong>Total cotizado</strong></td><td className="num"><strong>{formatMoney(toCents(quote.total))}</strong></td></tr>
        </tbody>
      </table>
      {error && <p className="error" role="alert">{error}</p>}
      {left ? (
        <button type="button" className="primary" onClick={convert} disabled={busy}>{busy ? "Creando pedido…" : "Convertir en pedido"}</button>
      ) : (
        <p className="muted small">Todo lo cotizado ya está en pedidos: cuando la caja los cobre, la cotización queda convertida.</p>
      )}
    </section>
  );
}

function OrderCreated({ order, onDone }: { order: Order; onDone: () => void }) {
  return (
    <div className="order-created" role="status">
      <div className="total-label">Código para pagar en caja</div>
      <div className="order-code" aria-label="Código del pedido">{order.code}</div>
      <div>Total {formatMoney(toCents(order.total))} (precio cotizado)</div>
      {order.warnings?.map((w) => (
        <p key={w.sku} className="warn-note small">
          {w.kind === "sin_existencias" ? `${w.name}: hay ${formatQty(w.available)}, no alcanza.` : `${w.name}: queda bajo el mínimo.`}
        </p>
      ))}
      <button type="button" className="primary" onClick={onDone}>Listo</button>
    </div>
  );
}

function VoidQuote({ id, onVoided }: { id: number; onVoided: () => void }) {
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function cancel() {
    setError(null);
    try {
      await api(`${URL}${id}/void/`, { method: "POST", body: { note } });
      onVoided();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <div className="sale-actions">
      <div className="row">
        <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Por qué se anula" aria-label="Motivo de la anulación" />
        <button type="button" className="danger-btn" onClick={cancel} disabled={!note.trim()}>Anular</button>
      </div>
      {error && <p className="error" role="alert">{error}</p>}
    </div>
  );
}
