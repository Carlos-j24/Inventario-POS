import { useEffect, useState, type FormEvent } from "react";

import { api, type PaymentMethod, type Register, type SaleDetail, type SaleReturn } from "../api";
import { formatMoney, formatQty, toCents } from "../money";

const METHODS: { method: PaymentMethod; label: string }[] = [
  { method: "CASH", label: "Efectivo" },
  { method: "CARD", label: "Tarjeta" },
  { method: "TRANSFER", label: "Transferencia" },
];

/** Lo que aún se puede devolver de cada línea: lo vendido menos lo ya devuelto. */
export function remaining(line: SaleDetail["lines"][number]): number {
  return Math.max(0, Number(line.quantity) - Number(line.returned_quantity));
}

/** Por qué no se puede anular, o null si se puede (mismas reglas que el backend). */
export function whyNotVoid(sale: SaleDetail): string | null {
  if (sale.status === "VOIDED") return "La venta ya está anulada.";
  if (sale.returns.length) return "Tiene devoluciones: ya no se puede anular. Haz otra devolución si hace falta.";
  if (!sale.shift_open) return "Su turno ya cerró y el arqueo no puede cambiar: haz una devolución.";
  return null;
}

/** Anular y devolver (spec 003, T4). Solo se muestra a quien tiene sales.void. */
export default function SaleActions({ sale, onDone }: { sale: SaleDetail; onDone: () => void }) {
  const [mode, setMode] = useState<"void" | "return" | null>(null);
  if (sale.status === "VOIDED") return null;
  const voidBlocked = whyNotVoid(sale);
  const canReturn = sale.lines.some((l) => remaining(l) > 0);

  return (
    <div className="sale-actions">
      {mode === null && (
        <div className="row">
          <button onClick={() => setMode("void")} disabled={!!voidBlocked} title={voidBlocked ?? undefined}>
            Anular venta
          </button>
          <button onClick={() => setMode("return")} disabled={!canReturn}>Devolver</button>
        </div>
      )}
      {mode === null && voidBlocked && <p className="muted small">{voidBlocked}</p>}
      {mode === "void" && <VoidForm sale={sale} onCancel={() => setMode(null)} onDone={onDone} />}
      {mode === "return" && <ReturnForm sale={sale} onCancel={() => setMode(null)} onDone={onDone} />}
    </div>
  );
}

function VoidForm({ sale, onCancel, onDone }: { sale: SaleDetail; onCancel: () => void; onDone: () => void }) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api(`/api/sales/${sale.id}/void/`, { method: "POST", body: { reason } });
      onDone();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="action-form" onSubmit={submit}>
      <h3>Anular {sale.number}</h3>
      <p className="muted small">
        Vuelve todo el stock y sus pagos ({formatMoney(toCents(sale.total))}) salen del arqueo de {sale.register}.
      </p>
      <label>
        Motivo
        <input value={reason} onChange={(e) => setReason(e.target.value)} autoFocus placeholder="Error de digitación" />
      </label>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="row">
        <button type="button" onClick={onCancel} disabled={busy}>Volver</button>
        <button className="danger-btn" disabled={busy || !reason.trim()}>Anular venta</button>
      </div>
    </form>
  );
}

function ReturnForm({ sale, onCancel, onDone }: { sale: SaleDetail; onCancel: () => void; onDone: () => void }) {
  const [qty, setQty] = useState<Record<number, string>>({});
  const [reason, setReason] = useState("");
  const [method, setMethod] = useState<PaymentMethod>("CASH");
  const [registers, setRegisters] = useState<Register[] | null>(null);
  const [shift, setShift] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Un UUID por intento: un reintento tras un fallo de red no devuelve dos veces.
  const [clientUuid] = useState(() => crypto.randomUUID());

  useEffect(() => {
    api<Register[]>("/api/cash/registers/")
      .then((rs) => {
        const open = rs.filter((r) => r.open_shift);
        setRegisters(open);
        // Por defecto, la caja de la venta si sigue abierta.
        setShift((open.find((r) => r.code === sale.register) ?? open[0])?.open_shift ?? null);
      })
      .catch((e) => setError(e.message));
  }, [sale.register]);

  const chosen = sale.lines
    .map((l) => ({ line: l, quantity: Number(qty[l.id] || 0) }))
    .filter((c) => c.quantity > 0);
  const over = chosen.find((c) => c.quantity > remaining(c.line));
  // Estimado para el supervisor: el backend calcula el valor exacto (con el resto exacto en la última parte).
  const estimate = chosen.reduce((sum, c) => sum + Math.round(toCents(c.line.unit_price) * c.quantity), 0);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!shift) return;
    setBusy(true);
    setError(null);
    try {
      await api<SaleReturn>(`/api/sales/${sale.id}/returns/`, {
        method: "POST",
        body: {
          client_uuid: clientUuid, shift, refund_method: method, reason,
          lines: chosen.map((c) => ({ line: c.line.id, quantity: String(c.quantity) })),
        },
      });
      onDone();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="action-form" onSubmit={submit}>
      <h3>Devolución de {sale.number}</h3>
      <table className="cart">
        <thead><tr><th>Producto</th><th className="num">Puede devolver</th><th>Devuelve</th></tr></thead>
        <tbody>
          {sale.lines.map((l) => (
            <tr key={l.id}>
              <td>{l.name}</td>
              <td className="num">{formatQty(remaining(l))} {l.unit}</td>
              <td>
                <input
                  className="qty"
                  type="number"
                  min="0"
                  step="any"
                  max={remaining(l)}
                  disabled={remaining(l) === 0}
                  value={qty[l.id] ?? ""}
                  onChange={(e) => setQty({ ...qty, [l.id]: e.target.value })}
                  aria-label={`Devolver ${l.name}`}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {over && <p className="error">{over.line.name}: solo se pueden devolver {formatQty(remaining(over.line))}.</p>}
      <label>
        Motivo
        <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="El cliente no lo necesitó" />
      </label>
      <div className="row">
        <label>
          Reembolso en
          <select value={method} onChange={(e) => setMethod(e.target.value as PaymentMethod)}>
            {METHODS.map((m) => <option key={m.method} value={m.method}>{m.label}</option>)}
          </select>
        </label>
        <label>
          Sale de la caja
          <select value={shift ?? ""} onChange={(e) => setShift(Number(e.target.value))} aria-label="Caja del reembolso">
            {registers?.map((r) => <option key={r.id} value={r.open_shift!}>{r.name}</option>)}
          </select>
        </label>
      </div>
      {registers && registers.length === 0 && (
        <p className="error">No hay ninguna caja con turno abierto: abre un turno para poder reembolsar.</p>
      )}
      <p>Reembolso estimado: <strong>{formatMoney(estimate)}</strong></p>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="row">
        <button type="button" onClick={onCancel} disabled={busy}>Volver</button>
        <button className="primary" disabled={busy || !chosen.length || !!over || !reason.trim() || !shift}>
          Registrar devolución
        </button>
      </div>
    </form>
  );
}
