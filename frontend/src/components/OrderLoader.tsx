import { useState, type FormEvent } from "react";

import { api, ApiError, type Order } from "../api";
import { formatMoney, toCents } from "../money";
import { isUnreachable } from "../offline";

/** Por qué un pedido no se puede cobrar, o null si está pendiente. */
export function whyNotPayable(order: Order): string | null {
  switch (order.status) {
    case "PENDING":
      return null;
    case "PAID":
      return `El pedido ${order.code} ya fue cobrado${order.sale_number ? ` (venta ${order.sale_number})` : ""}.`;
    case "CANCELLED":
      return `El pedido ${order.code} fue cancelado.`;
    case "EXPIRED":
      return `El pedido ${order.code} venció: era de otro día.`;
  }
}

/** La caja carga un pedido por su código de 4 dígitos o eligiéndolo entre los pendientes de hoy. */
export default function OrderLoader({ onLoad }: { onLoad: (order: Order) => void }) {
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<Order[] | null>(null);

  function explain(err: unknown) {
    if (isUnreachable(err)) setError("Sin conexión: los pedidos se cobran con red. Puedes vender directo.");
    else if (err instanceof ApiError && err.status === 404) setError(`No hay un pedido de hoy con el código ${code}.`);
    else setError((err as Error).message);
  }

  function take(order: Order) {
    const reason = whyNotPayable(order);
    if (reason) return setError(reason);
    setError(null);
    setCode("");
    setPending(null);
    onLoad(order);
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!/^\d{4}$/.test(code)) return setError("El código tiene 4 dígitos.");
    try {
      take(await api<Order>(`/api/orders/code/${code}/`));
    } catch (err) {
      explain(err);
    }
  }

  async function togglePending() {
    if (pending) return setPending(null);
    try {
      setPending(await api<Order[]>("/api/orders/"));
      setError(null);
    } catch (err) {
      explain(err);
    }
  }

  return (
    <div className="order-loader">
      <form className="row" onSubmit={submit}>
        <input
          inputMode="numeric"
          maxLength={4}
          placeholder="Código de pedido"
          value={code}
          onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
          aria-label="Código de pedido"
        />
        <button>Cargar pedido</button>
        <button type="button" className="link" onClick={togglePending}>
          {pending ? "Ocultar pendientes" : "Pedidos pendientes"}
        </button>
      </form>
      {error && <p className="error" role="alert">{error}</p>}
      {pending && (
        <ul className="results">
          {pending.length === 0 && <li className="muted">No hay pedidos pendientes hoy.</li>}
          {pending.map((o) => (
            <li key={o.id}>
              <button onClick={() => take(o)}>
                <span><strong className="code-chip">{o.code}</strong> {formatMoney(toCents(o.total))}</span>
                <span className="muted">{o.salesperson} · {o.lines.length} producto(s)</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
