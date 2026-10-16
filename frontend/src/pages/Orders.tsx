import { useCallback, useEffect, useRef, useState } from "react";

import { api, type Order, type Product } from "../api";
import { addToCart, cartTotalCents, quantityError, type CartLine } from "../cart";
import CartTable from "../components/CartTable";
import ProductSearch from "../components/ProductSearch";
import { formatMoney, formatQty, toCents } from "../money";
import { isUnreachable } from "../offline";

/** Spec 002: el vendedor arma el pedido y le da al cliente un código para pagar en caja. */
export default function Orders() {
  const [products, setProducts] = useState<Product[]>([]);
  const [lines, setLines] = useState<CartLine[]>([]);
  const [created, setCreated] = useState<Order | null>(null);
  const [mine, setMine] = useState<Order[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Un UUID por intento: si la red falla y se reintenta, el servidor no duplica el pedido.
  const [clientUuid, setClientUuid] = useState(() => crypto.randomUUID());
  const searchRef = useRef<HTMLInputElement>(null);

  const loadMine = useCallback(
    () => api<Order[]>("/api/orders/?mine=1").then(setMine).catch(() => {}),
    [],
  );

  useEffect(() => {
    api<Product[]>("/api/catalog/products/").then(setProducts).catch((e) => setError(e.message));
    loadMine();
    const timer = window.setInterval(loadMine, 30_000); // los cobrados desaparecen solos de la lista
    return () => window.clearInterval(timer);
  }, [loadMine]);

  const total = cartTotalCents(lines);
  const valid = lines.length > 0 && lines.every((l) => quantityError(l) === null);

  async function createOrder() {
    setBusy(true);
    setError(null);
    try {
      const order = await api<Order>("/api/orders/", {
        method: "POST",
        body: {
          client_uuid: clientUuid,
          lines: lines.map((l) => ({ product: l.product.id, unit: l.unit, quantity: String(l.quantity) })),
        },
      });
      setCreated(order);
      setLines([]);
      setClientUuid(crypto.randomUUID());
      loadMine();
    } catch (err) {
      setError(
        isUnreachable(err)
          ? "Sin conexión: los pedidos necesitan red porque se cobran en otro equipo. Intenta de nuevo."
          : (err as Error).message,
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="pos">
      <section className="card">
        <h2>Nuevo pedido</h2>
        <ProductSearch
          products={products}
          onPick={(p, u) => { setLines((ls) => addToCart(ls, p, u)); setCreated(null); }}
          inputRef={searchRef}
        />
        <CartTable lines={lines} onChange={setLines} emptyText="Busca o escanea los productos que se lleva el cliente." />
        <MyOrders orders={mine} onChanged={loadMine} />
      </section>

      <aside className="card summary">
        {created ? (
          <OrderCode order={created} onNew={() => { setCreated(null); searchRef.current?.focus(); }} />
        ) : (
          <>
            <div className="total-label">Total del pedido</div>
            <div className="total">{formatMoney(total)}</div>
            <button className="primary big" disabled={!valid || busy} onClick={createOrder}>
              {busy ? "Creando…" : "Crear pedido"}
            </button>
            {lines.length > 0 && <button className="link" onClick={() => setLines([])}>Vaciar</button>}
          </>
        )}
        {error && <p className="error" role="alert">{error}</p>}
      </aside>
    </div>
  );
}

function OrderCode({ order, onNew }: { order: Order; onNew: () => void }) {
  return (
    <div className="order-created" role="status">
      <div className="total-label">Código para pagar en caja</div>
      <div className="order-code" aria-label="Código del pedido">{order.code}</div>
      <div>Total {formatMoney(toCents(order.total))}</div>
      {order.warnings?.map((w) => (
        <p key={w.sku} className="warn-note small">
          {w.kind === "sin_existencias"
            ? `${w.name}: hay ${formatQty(w.available)}, no alcanza.`
            : `${w.name}: queda bajo el mínimo.`}
        </p>
      ))}
      <button className="primary" onClick={onNew}>Nuevo pedido</button>
    </div>
  );
}

function MyOrders({ orders, onChanged }: { orders: Order[]; onChanged: () => void }) {
  const [confirming, setConfirming] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function cancel(id: number) {
    setError(null);
    try {
      await api(`/api/orders/${id}/cancel/`, { method: "POST" });
      setConfirming(null);
      onChanged();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <div className="my-orders">
      <h3>Mis pedidos pendientes de hoy</h3>
      {orders.length === 0 && <p className="muted">Ninguno.</p>}
      {error && <p className="error">{error}</p>}
      <ul className="plain-list">
        {orders.map((o) => (
          <li key={o.id} className="row spread">
            <span>
              <strong className="code-chip">{o.code}</strong> {formatMoney(toCents(o.total))}
              <span className="muted"> · {o.lines.length} producto(s) · {new Date(o.created_at).toLocaleTimeString("es-CO", { hour: "2-digit", minute: "2-digit" })}</span>
            </span>
            {confirming === o.id ? (
              <span className="row">
                <span>¿Cancelar?</span>
                <button onClick={() => cancel(o.id)}>Sí, cancelar</button>
                <button className="link" onClick={() => setConfirming(null)}>No</button>
              </span>
            ) : (
              <button className="link" onClick={() => setConfirming(o.id)} aria-label={`Cancelar pedido ${o.code}`}>
                Cancelar
              </button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
