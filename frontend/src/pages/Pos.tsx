import { useEffect, useRef, useState, type FormEvent } from "react";

import { api, type Order, type PaymentMethod, type Product, type Register, type Sale, type Shift } from "../api";
import { useAuth } from "../auth";
import { fetchWithCache } from "../cache";
import { addToCart, cartTotalCents, checkPayments, linePriceCents, orderToCart, quantityError, type CartLine } from "../cart";
import CartTable from "../components/CartTable";
import OrderLoader from "../components/OrderLoader";
import ProductSearch from "../components/ProductSearch";
import { centsToApi, formatMoney, toCents } from "../money";
import { isUnreachable, toOfflineBody, type QueuedSale } from "../offline";
import { useSync } from "../sync";

const REGISTER_KEY = "pos.register";

function rememberRegister(id: number | null) {
  try {
    if (id == null) localStorage.removeItem(REGISTER_KEY);
    else localStorage.setItem(REGISTER_KEY, String(id));
  } catch {
    /* sin almacenamiento local: solo se pierde la comodidad de recordar la caja */
  }
}

function rememberedRegister(): number | null {
  try {
    const v = localStorage.getItem(REGISTER_KEY);
    return v ? Number(v) : null;
  } catch {
    return null;
  }
}

export default function Pos() {
  const [registers, setRegisters] = useState<Register[] | null>(null);
  const [registerId, setRegisterId] = useState<number | null>(rememberedRegister);
  const [error, setError] = useState<string | null>(null);

  const reload = () =>
    fetchWithCache<Register[]>("/api/cash/registers/")
      .then((r) => setRegisters(r.data))
      .catch((e) => setError(e.message));

  useEffect(() => {
    reload();
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!registers) return <p className="muted">Cargando cajas…</p>;

  const register = registers.find((r) => r.id === registerId);
  if (!register) {
    return (
      <section className="card narrow">
        <h2>¿En qué caja estás?</h2>
        {registers.length === 0 && <p className="muted">No hay cajas creadas. El administrador debe crearlas.</p>}
        <div className="choices">
          {registers.map((r) => (
            <button key={r.id} onClick={() => { rememberRegister(r.id); setRegisterId(r.id); }}>
              <strong>{r.name}</strong>
              <span className="muted">{r.open_shift ? "Turno abierto" : "Sin turno"}</span>
            </button>
          ))}
        </div>
      </section>
    );
  }

  const changeRegister = () => { rememberRegister(null); setRegisterId(null); reload(); };

  if (!register.open_shift) return <OpenShift register={register} onOpened={reload} onBack={changeRegister} />;
  return <Selling register={register} shiftId={register.open_shift} onShiftClosed={changeRegister} />;
}

function OpenShift({ register, onOpened, onBack }: { register: Register; onOpened: () => void; onBack: () => void }) {
  const [float, setFloat] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    try {
      await api("/api/cash/shifts/", {
        method: "POST",
        body: { register: register.id, opening_float: centsToApi(toCents(float)) },
      });
      onOpened();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <form className="card narrow" onSubmit={submit}>
      <h2>Abrir turno · {register.name}</h2>
      <label>
        Base en efectivo
        <input inputMode="decimal" value={float} onChange={(e) => setFloat(e.target.value)} autoFocus placeholder="0" />
      </label>
      {error && <p className="error">{error}</p>}
      <div className="row">
        <button type="button" onClick={onBack}>Cambiar de caja</button>
        <button className="primary">Abrir turno</button>
      </div>
    </form>
  );
}

function Selling({ register, shiftId, onShiftClosed }: { register: Register; shiftId: number; onShiftClosed: () => void }) {
  const [products, setProducts] = useState<Product[]>([]);
  const [lines, setLines] = useState<CartLine[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const [checkout, setCheckout] = useState(false);
  const [closing, setClosing] = useState(false);
  const [lastSale, setLastSale] = useState<Sale | null>(null);
  const [lastQueued, setLastQueued] = useState<QueuedSale | null>(null);
  const [catalogDate, setCatalogDate] = useState<string | null>(null);
  const [order, setOrder] = useState<Order | null>(null); // pedido que se está cobrando (spec 002)
  const searchRef = useRef<HTMLInputElement>(null);
  const { user } = useAuth();
  const { online, pending, enqueue } = useSync();

  // Se vuelve a pedir al recuperar la conexión, para dejar de vender con precios de la copia.
  useEffect(() => {
    fetchWithCache<Product[]>("/api/catalog/products/")
      .then((r) => { setProducts(r.data); setCatalogDate(r.staleSince); })
      .catch((e) => setNotice(e.message));
  }, [online]);

  const total = cartTotalCents(lines);
  const lineErrors = lines.map(quantityError);
  const canCharge = lines.length > 0 && lineErrors.every((e) => e === null);

  function loadOrder(o: Order) {
    try {
      setLines(orderToCart(o, products));
      setOrder(o);
      setNotice(null);
      setLastSale(null);
      setLastQueued(null);
    } catch (err) {
      setNotice((err as Error).message);
    }
  }

  function dropOrder() {
    setOrder(null);
    setLines([]);
    searchRef.current?.focus();
  }

  function add(product: Product, unit: string) {
    setLines((ls) => addToCart(ls, product, unit));
    setNotice(null);
    setLastSale(null);
    setLastQueued(null);
  }

  if (closing) return <CloseShift shiftId={shiftId} onCancel={() => setClosing(false)} onClosed={onShiftClosed} />;

  // Cerrar exige el servidor y todas las ventas enviadas: si no, el arqueo quedaría incompleto.
  const closeBlocked = !online
    ? "Sin conexión: el turno se cierra cuando vuelva la red."
    : pending.length
      ? "Hay ventas sin enviar: espera a que se sincronicen."
      : null;

  return (
    <div className="pos">
      <section className="card">
        <div className="row spread">
          <h2>{register.name}</h2>
          <button onClick={() => setClosing(true)} disabled={!!closeBlocked} title={closeBlocked ?? undefined}>
            Cerrar turno
          </button>
        </div>
        {catalogDate && (
          <p className="warn-note">
            Sin conexión: precios de la copia guardada el {new Date(catalogDate).toLocaleString("es-CO")}; las
            ventas se guardan en este equipo y se envían al volver la red.
          </p>
        )}
        {order ? (
          <div className="order-banner" role="status">
            <span>
              Cobrando el pedido <strong className="code-chip">{order.code}</strong> de {order.salesperson}. Puedes
              bajar cantidades o quitar lo que el cliente no lleve.
            </span>
            <button className="link" onClick={dropOrder}>Quitar pedido</button>
          </div>
        ) : (
          <>
            <ProductSearch products={products} onPick={add} inputRef={searchRef} />
            {lines.length === 0 && <OrderLoader onLoad={loadOrder} />}
          </>
        )}
        {notice && <p className="error">{notice}</p>}
        <CartTable lines={lines} onChange={setLines} emptyText="Escanea o busca un producto para empezar." />
      </section>

      <aside className="card summary">
        <div className="total-label">Total</div>
        <div className="total" data-testid="cart-total">{formatMoney(total)}</div>
        <button className="primary big" disabled={!canCharge} onClick={() => setCheckout(true)}>
          Cobrar
        </button>
        {lines.length > 0 && <button className="link" onClick={() => setLines([])}>Vaciar</button>}
        {lastSale && (
          <div className="done" role="status">
            <strong>Venta {lastSale.number}</strong>
            <span>Total {formatMoney(toCents(lastSale.total))}</span>
            {lastSale.payments.filter((p) => toCents(p.change) > 0).map((p) => (
              <span key={p.method} className="change">Vueltas {formatMoney(toCents(p.change))}</span>
            ))}
          </div>
        )}
        {lastQueued && (
          pending.some((p) => p.client_uuid === lastQueued.client_uuid) ? (
            <div className="done queued" role="status">
              <strong>Venta guardada sin conexión</strong>
              <span>Total {formatMoney(lastQueued.totalCents)}</span>
              <span className="muted small">Se enviará sola al volver la red.</span>
            </div>
          ) : (
            <div className="done" role="status">
              <strong>Venta sin conexión enviada</strong>
              <span>Total {formatMoney(lastQueued.totalCents)}</span>
            </div>
          )
        )}
      </aside>

      {checkout && user && (
        <Checkout
          shiftId={shiftId}
          lines={lines}
          totalCents={total}
          username={user.username}
          queue={enqueue}
          order={order}
          onCancel={() => setCheckout(false)}
          onPaid={(sale) => {
            setCheckout(false);
            setLines([]);
            setOrder(null);
            setLastSale(sale);
            searchRef.current?.focus();
          }}
          onQueued={(item) => {
            setCheckout(false);
            setLines([]);
            setLastQueued(item);
            searchRef.current?.focus();
          }}
        />
      )}
    </div>
  );
}

const METHODS: { method: PaymentMethod; label: string }[] = [
  { method: "CASH", label: "Efectivo" },
  { method: "CARD", label: "Tarjeta" },
  { method: "TRANSFER", label: "Transferencia" },
];

export function Checkout({ shiftId, lines, totalCents, username, queue, order = null, onCancel, onPaid, onQueued }: {
  shiftId: number;
  lines: CartLine[];
  totalCents: number;
  username: string;
  /** Si se cobra un pedido: va order + order_lines en vez de líneas sueltas, y sin red no va a la cola. */
  order?: Order | null;
  /** Guarda la venta en la cola local cuando el servidor no responde. */
  queue: (item: QueuedSale) => Promise<void>;
  onCancel: () => void;
  onPaid: (sale: Sale) => void;
  onQueued: (item: QueuedSale) => void;
}) {
  const [amounts, setAmounts] = useState<Record<PaymentMethod, string>>({ CASH: "", CARD: "", TRANSFER: "" });
  const [refs, setRefs] = useState<Record<PaymentMethod, string>>({ CASH: "", CARD: "", TRANSFER: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Un UUID por intento de cobro: si la red falla y se reintenta, el servidor no duplica la venta.
  const [clientUuid] = useState(() => crypto.randomUUID());

  const drafts = METHODS.map(({ method }) => ({ method, amountCents: toCents(amounts[method] || 0) }));
  const check = checkPayments(totalCents, drafts);

  async function pay(e: FormEvent) {
    e.preventDefault();
    if (check.error) return;
    setBusy(true);
    setError(null);
    const items = order
      ? { order: order.id, order_lines: lines.map((l) => ({ order_line: l.order!.lineId, quantity: String(l.quantity) })) }
      : { lines: lines.map((l) => ({ product: l.product.id, unit: l.unit, quantity: String(l.quantity) })) };
    const body = {
      client_uuid: clientUuid,
      shift: shiftId,
      ...items,
      payments: check.payments.map((p) => ({
        method: p.method,
        amount: centsToApi(p.amountCents),
        reference: refs[p.method],
      })),
    };
    try {
      onPaid(await api<Sale>("/api/sales/", { method: "POST", body }));
    } catch (err) {
      if (!isUnreachable(err)) {
        setError((err as Error).message);
        return;
      }
      if (order) {
        // El pedido vive en el servidor: sin red no se puede marcar como cobrado.
        setError("Sin conexión: los pedidos se cobran con red. Intenta de nuevo; el cobro no se duplica.");
        return;
      }
      // Sin servidor: la venta se guarda con el mismo client_uuid. Si el primer envío sí llegó,
      // el servidor la reconoce al sincronizar y no la duplica.
      const item: QueuedSale = {
        client_uuid: clientUuid,
        username,
        createdAt: new Date().toISOString(),
        totalCents,
        body: toOfflineBody(body, lines.map(linePriceCents)),
        status: "pending",
      };
      try {
        await queue(item);
        onQueued(item);
      } catch {
        setError("Sin conexión y no se pudo guardar la venta en este equipo. No entregues la mercancía.");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="overlay" role="dialog" aria-label="Cobrar">
      <form className="card modal" onSubmit={pay}>
        <h2>Cobrar {formatMoney(totalCents)}</h2>
        {METHODS.map(({ method, label }) => (
          <div className="payment" key={method}>
            <label>
              {label}
              <input
                inputMode="decimal"
                value={amounts[method]}
                onChange={(e) => setAmounts({ ...amounts, [method]: e.target.value })}
                placeholder="0"
                autoFocus={method === "CASH"}
              />
            </label>
            {method !== "CASH" && (
              <label>
                Referencia
                <input value={refs[method]} onChange={(e) => setRefs({ ...refs, [method]: e.target.value })} />
              </label>
            )}
            <button
              type="button"
              onClick={() => {
                const others = drafts.filter((d) => d.method !== method).reduce((s, d) => s + d.amountCents, 0);
                setAmounts({ ...amounts, [method]: centsToApi(Math.max(0, totalCents - others)) });
              }}
            >
              Exacto
            </button>
          </div>
        ))}
        <div className="checkout-status">
          {check.error ? (
            <span className="error">
              {check.error}
              {check.missingCents > 0 && ` Faltan ${formatMoney(check.missingCents)}.`}
            </span>
          ) : (
            <span className="change">Vueltas: {formatMoney(check.changeCents)}</span>
          )}
        </div>
        {error && <p className="error" role="alert">{error}</p>}
        <div className="row">
          <button type="button" onClick={onCancel} disabled={busy}>Volver</button>
          <button className="primary" disabled={busy || !!check.error}>{busy ? "Registrando…" : "Confirmar pago"}</button>
        </div>
      </form>
    </div>
  );
}

export function CloseShift({ shiftId, onCancel, onClosed }: { shiftId: number; onCancel: () => void; onClosed: () => void }) {
  const [shift, setShift] = useState<Shift | null>(null);
  const [counted, setCounted] = useState("");
  const [notes, setNotes] = useState("");
  const [closed, setClosed] = useState<Shift | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Shift>(`/api/cash/shifts/${shiftId}/`).then(setShift).catch((e) => setError(e.message));
  }, [shiftId]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    try {
      setClosed(await api<Shift>(`/api/cash/shifts/${shiftId}/close/`, {
        method: "POST",
        body: { counted_cash: centsToApi(toCents(counted)), notes },
      }));
    } catch (err) {
      setError((err as Error).message);
    }
  }

  if (error) return <p className="error">{error}</p>;
  if (!shift) return <p className="muted">Cargando turno…</p>;

  if (closed) {
    const diff = toCents(closed.difference ?? 0);
    return (
      <section className="card narrow">
        <h2>Turno cerrado</h2>
        <p>Esperado {formatMoney(toCents(closed.expected_cash ?? 0))} · Contado {formatMoney(toCents(closed.counted_cash ?? 0))}</p>
        <p className={diff === 0 ? "change" : "error"}>
          {diff === 0 ? "Caja cuadrada." : diff < 0 ? `Faltante de ${formatMoney(-diff)}.` : `Sobrante de ${formatMoney(diff)}.`}
        </p>
        <button className="primary" onClick={onClosed}>Listo</button>
      </section>
    );
  }

  const s = shift.summary;
  return (
    <form className="card narrow" onSubmit={submit}>
      <h2>Cerrar turno</h2>
      <table className="plain">
        <tbody>
          <tr><td>Ventas</td><td className="num">{s.sales}</td></tr>
          {METHODS.filter((m) => m.method !== "CASH").map(({ method, label }) => (
            <tr key={method}><td>{label}</td><td className="num">{formatMoney(toCents(s.by_method[method]))}</td></tr>
          ))}
        </tbody>
      </table>
      <p className="muted">
        Arqueo a ciegas: cuenta el efectivo del cajón (con la base). El esperado se muestra al cerrar.
      </p>
      <label>
        Efectivo contado
        <input inputMode="decimal" value={counted} onChange={(e) => setCounted(e.target.value)} autoFocus />
      </label>
      <label>
        Notas
        <input value={notes} onChange={(e) => setNotes(e.target.value)} />
      </label>
      <div className="row">
        <button type="button" onClick={onCancel}>Seguir vendiendo</button>
        <button className="primary" disabled={!counted}>Cerrar turno</button>
      </div>
    </form>
  );
}
