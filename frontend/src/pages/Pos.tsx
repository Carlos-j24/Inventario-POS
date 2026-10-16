import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";

import { api, type PaymentMethod, type Product, type Register, type Sale, type Shift } from "../api";
import {
  cartTotalCents, checkPayments, findByCode, lineTotalCents, quantityError, searchProducts, unitPriceCents,
  type CartLine,
} from "../cart";
import { centsToApi, formatMoney, formatQty, toCents } from "../money";

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
    api<Register[]>("/api/cash/registers/")
      .then(setRegisters)
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
  const [query, setQuery] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [checkout, setCheckout] = useState(false);
  const [closing, setClosing] = useState(false);
  const [lastSale, setLastSale] = useState<Sale | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api<Product[]>("/api/catalog/products/").then(setProducts).catch((e) => setNotice(e.message));
  }, []);

  const results = useMemo(() => searchProducts(products, query), [products, query]);
  const total = cartTotalCents(lines);
  const lineErrors = lines.map(quantityError);
  const canCharge = lines.length > 0 && lineErrors.every((e) => e === null);

  function add(product: Product, unit = product.base_unit) {
    setLines((ls) => {
      const same = ls.find((l) => l.product.id === product.id && l.unit === unit);
      if (same) return ls.map((l) => (l === same ? { ...l, quantity: l.quantity + 1 } : l));
      return [...ls, { key: crypto.randomUUID(), product, unit, quantity: 1 }];
    });
    setQuery("");
    setNotice(null);
    setLastSale(null);
    searchRef.current?.focus();
  }

  function onSearchSubmit(e: FormEvent) {
    e.preventDefault();
    // El lector de código de barras escribe el código y presiona Enter.
    const hit = findByCode(products, query);
    if (hit) add(hit.product, hit.unit);
    else if (results.length === 1) add(results[0]);
    else setNotice(results.length ? "Elige el producto de la lista." : `No se encontró "${query}".`);
  }

  function update(key: string, patch: Partial<CartLine>) {
    setLines((ls) => ls.map((l) => (l.key === key ? { ...l, ...patch } : l)));
  }

  if (closing) return <CloseShift shiftId={shiftId} onCancel={() => setClosing(false)} onClosed={onShiftClosed} />;

  return (
    <div className="pos">
      <section className="card">
        <div className="row spread">
          <h2>{register.name}</h2>
          <button onClick={() => setClosing(true)}>Cerrar turno</button>
        </div>
        <form onSubmit={onSearchSubmit}>
          <input
            ref={searchRef}
            className="search"
            placeholder="Código de barras, SKU o nombre…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoFocus
            aria-label="Buscar producto"
          />
        </form>
        {results.length > 0 && (
          <ul className="results">
            {results.map((p) => (
              <li key={p.id}>
                <button onClick={() => add(p)}>
                  <span>{p.name}</span>
                  <span className="muted">{p.sku} · {formatMoney(toCents(p.sale_price))}/{p.base_unit}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
        {notice && <p className="error">{notice}</p>}

        <table className="cart">
          <thead>
            <tr><th>Producto</th><th>Cantidad</th><th>Unidad</th><th className="num">Precio</th><th className="num">Total</th><th /></tr>
          </thead>
          <tbody>
            {lines.map((l, i) => (
              <tr key={l.key}>
                <td>{l.product.name}{lineErrors[i] && <div className="error small">{lineErrors[i]}</div>}</td>
                <td>
                  <input
                    className="qty"
                    type="number"
                    min="0"
                    step={l.product.allows_fractions ? "0.001" : "1"}
                    value={l.quantity}
                    onChange={(e) => update(l.key, { quantity: Number(e.target.value) })}
                    aria-label={`Cantidad de ${l.product.name}`}
                  />
                </td>
                <td>
                  <select value={l.unit} onChange={(e) => update(l.key, { unit: e.target.value })}>
                    <option value={l.product.base_unit}>{l.product.base_unit}</option>
                    {l.product.units.map((u) => (
                      <option key={u.unit} value={u.unit}>{u.unit} ({formatQty(u.factor)} {l.product.base_unit})</option>
                    ))}
                  </select>
                </td>
                <td className="num">{formatMoney(unitPriceCents(l.product, l.unit))}</td>
                <td className="num">{formatMoney(lineTotalCents(l))}</td>
                <td>
                  <button className="link" onClick={() => setLines((ls) => ls.filter((x) => x.key !== l.key))} aria-label={`Quitar ${l.product.name}`}>
                    ✕
                  </button>
                </td>
              </tr>
            ))}
            {lines.length === 0 && (
              <tr><td colSpan={6} className="muted center">Escanea o busca un producto para empezar.</td></tr>
            )}
          </tbody>
        </table>
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
      </aside>

      {checkout && (
        <Checkout
          shiftId={shiftId}
          lines={lines}
          totalCents={total}
          onCancel={() => setCheckout(false)}
          onPaid={(sale) => {
            setCheckout(false);
            setLines([]);
            setLastSale(sale);
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

export function Checkout({ shiftId, lines, totalCents, onCancel, onPaid }: {
  shiftId: number;
  lines: CartLine[];
  totalCents: number;
  onCancel: () => void;
  onPaid: (sale: Sale) => void;
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
    try {
      const sale = await api<Sale>("/api/sales/", {
        method: "POST",
        body: {
          client_uuid: clientUuid,
          shift: shiftId,
          lines: lines.map((l) => ({ product: l.product.id, unit: l.unit, quantity: String(l.quantity) })),
          payments: check.payments.map((p) => ({
            method: p.method,
            amount: centsToApi(p.amountCents),
            reference: refs[p.method],
          })),
        },
      });
      onPaid(sale);
    } catch (err) {
      setError((err as Error).message);
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
