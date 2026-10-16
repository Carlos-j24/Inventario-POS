import { useEffect, useState } from "react";

import { api } from "../api";
import { useCan } from "../auth";
import { formatMoney, formatQty, toCents } from "../money";
import { SaleDetailView } from "./Sales";

interface ReviewItem {
  id: number;
  number: string;
  seller: string;
  total: string;
  offline: boolean;
  occurred_at: string;
  reasons: string[];
  lines: { id: number; product: string; unit: string; quantity: string; unit_price: string; catalog_price: string }[];
}

/** Bandeja de ventas marcadas (precio distinto, stock negativo o turno ya cerrado). */
export default function Review() {
  const [items, setItems] = useState<ReviewItem[] | null>(null);
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<number | null>(null);
  const can = useCan();

  const load = () => api<ReviewItem[]>("/api/sales/review/").then(setItems).catch((e) => setError(e.message));

  useEffect(() => {
    load();
  }, []);

  async function markReviewed(id: number) {
    try {
      await api(`/api/sales/${id}/review/`, { method: "POST", body: { note: notes[id] ?? "" } });
      setItems((xs) => xs?.filter((x) => x.id !== id) ?? null);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  if (!items) return error ? <p className="error">{error}</p> : <p className="muted">Cargando…</p>;

  return (
    <section className="card">
      <h2>Ventas por revisar</h2>
      {error && <p className="error">{error}</p>}
      {items.length === 0 && <p className="muted">Nada pendiente.</p>}
      {items.map((s) => (
        <article key={s.id} className="review-item">
          <div className="row spread">
            <strong>
              {s.number} · {formatMoney(toCents(s.total))}
            </strong>
            <span className="muted">
              {s.seller} · {new Date(s.occurred_at).toLocaleString("es-CO")} {s.offline && "· sin conexión"}
            </span>
          </div>
          <div className="row">
            {s.reasons.map((r) => (
              <span key={r} className="badge warn">{r}</span>
            ))}
          </div>
          <ul className="plain-list">
            {s.lines.map((l) => (
              <li key={l.id}>
                {formatQty(l.quantity)} {l.unit} {l.product} a {formatMoney(toCents(l.unit_price))}
                {l.unit_price !== l.catalog_price && (
                  <span className="muted"> (catálogo {formatMoney(toCents(l.catalog_price))})</span>
                )}
              </li>
            ))}
          </ul>
          <div className="row">
            <input
              placeholder="Qué se hizo (opcional)"
              value={notes[s.id] ?? ""}
              onChange={(e) => setNotes({ ...notes, [s.id]: e.target.value })}
              aria-label={`Nota para ${s.number}`}
            />
            <button className="primary" onClick={() => markReviewed(s.id)}>Marcar revisada</button>
            <button className="link" onClick={() => setOpen(open === s.id ? null : s.id)}>
              {open === s.id ? "Ocultar venta" : "Ver venta"}
            </button>
          </div>
          {open === s.id && (
            <div className="card nested">
              <SaleDetailView id={s.id} canAct={can("sales.void")} onChanged={load} />
            </div>
          )}
        </article>
      ))}
    </section>
  );
}
