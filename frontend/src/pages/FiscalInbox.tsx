import { useCallback, useEffect, useState } from "react";

import { api, type FiscalDocumentDetail, type FiscalDocumentRow, type FiscalInbox as Inbox, type FiscalStatus } from "../api";
import { useCan } from "../auth";
import { formatMoney, toCents } from "../money";

const FILTERS: { id: "" | FiscalStatus; label: string }[] = [
  { id: "", label: "Por atender" },
  { id: "PENDING", label: "Pendientes" },
  { id: "REJECTED", label: "Rechazados" },
  { id: "VALIDATED", label: "Validados" },
];

const EVENT_LABEL: Record<string, string> = {
  created: "Creado",
  validated: "Validado por la DIAN",
  rejected: "Rechazado",
  unavailable: "Sin respuesta del proveedor",
  retry: "Reintento",
};

const when = (iso: string) => new Date(iso).toLocaleString("es-CO", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

export function inboxUrl(filter: "" | FiscalStatus): string {
  return `/api/invoicing/documents/${filter ? `?status=${filter}` : ""}`;
}

function StatusBadge({ doc }: { doc: FiscalDocumentRow }) {
  if (doc.status === "REJECTED") return <span className="badge danger">Rechazado</span>;
  if (doc.status === "VALIDATED") return <span className="badge">Validado</span>;
  if (doc.alert === "overdue") return <span className="badge danger">Plazo vencido</span>;
  if (doc.alert === "due_soon") return <span className="badge warn">Vence pronto</span>;
  if (doc.waiting_for) return <span className="badge">Espera {doc.waiting_for}</span>;
  return <span className="badge warn">Pendiente</span>;
}

/** Spec 005, T4: documentos electrónicos pendientes y rechazados, con su historial. */
export default function FiscalInbox() {
  const [filter, setFilter] = useState<"" | FiscalStatus>("");
  const [inbox, setInbox] = useState<Inbox | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setInbox(await api<Inbox>(inboxUrl(filter)));
    } catch (err) {
      setError((err as Error).message);
    }
  }, [filter]);

  useEffect(() => {
    load();
  }, [load]);

  const s = inbox?.summary;
  return (
    <div className="two-cols sales-page">
      <section className="card">
        <h2>Documentos DIAN</h2>
        {s && (
          <p className="row" aria-label="Resumen">
            <span className="badge warn">{s.pending} pendientes</span>
            <span className={s.rejected ? "badge danger" : "badge"}>{s.rejected} rechazados</span>
            {s.overdue > 0 && <span className="badge danger">{s.overdue} con plazo vencido</span>}
            {s.due_soon > 0 && <span className="badge warn">{s.due_soon} por vencer</span>}
          </p>
        )}
        <div className="row filters">
          {FILTERS.map((f) => (
            <button key={f.id} className={f.id === filter ? "tab active" : "tab"} aria-pressed={f.id === filter} onClick={() => setFilter(f.id)}>
              {f.label}
            </button>
          ))}
        </div>
        {error && <p className="error" role="alert">{error}</p>}
        {inbox && inbox.results.length === 0 && <p className="muted">Nada por aquí.</p>}
        {inbox && inbox.results.length > 0 && (
          <div className="table-wrap">
            <table className="cart sales-list" aria-label="Documentos">
              <thead>
                <tr><th>Documento</th><th>Venta</th><th>Cliente</th><th className="num">Total</th><th>Estado</th></tr>
              </thead>
              <tbody>
                {inbox.results.map((d) => (
                  <tr key={d.id} className={d.id === selected ? "selected" : ""} onClick={() => setSelected(d.id)}>
                    <td>
                      <button className="link" onClick={() => setSelected(d.id)}>{d.code}</button>
                      <div className="muted small">{d.kind_label}</div>
                    </td>
                    <td>{d.sale_number} <span className="muted small">{d.register}</span></td>
                    <td>{d.customer}</td>
                    <td className="num">{formatMoney(toCents(d.total))}</td>
                    <td><StatusBadge doc={d} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      <section className="card">
        {selected ? <DocumentDetail id={selected} onChanged={load} /> : <p className="muted">Elige un documento para ver su historial.</p>}
      </section>
    </div>
  );
}

function DocumentDetail({ id, onChanged }: { id: number; onChanged: () => void }) {
  const [doc, setDoc] = useState<FiscalDocumentDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const can = useCan();

  useEffect(() => {
    setDoc(null);
    setError(null);
    api<FiscalDocumentDetail>(`/api/invoicing/documents/${id}/`).then(setDoc).catch((err: Error) => setError(err.message));
  }, [id]);

  async function retry() {
    setBusy(true);
    setError(null);
    try {
      setDoc(await api<FiscalDocumentDetail>(`/api/invoicing/documents/${id}/retry/`, { method: "POST" }));
      onChanged();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (!doc) return error ? <p className="error" role="alert">{error}</p> : <p className="muted">Cargando…</p>;
  return (
    <div className="sale-detail">
      <h2>{doc.code}</h2>
      <p className="muted">
        {doc.kind_label} de la venta {doc.sale_number} · {doc.customer} · {formatMoney(toCents(doc.total))}
        {doc.corrects && <> · corrige {doc.corrects}</>}
      </p>
      <p><StatusBadge doc={doc} /> {doc.attempts > 0 && <span className="muted small">{doc.attempts} intento(s)</span>}</p>
      {doc.status === "PENDING" && <p className="muted small">Plazo para transmitir: {when(doc.deadline)}{doc.next_attempt_at && ` · próximo intento ${when(doc.next_attempt_at)}`}</p>}
      {doc.last_error && <p className="error">{doc.last_error}</p>}
      {doc.cude && <p className="small">CUDE: <code>{doc.cude}</code></p>}
      {doc.status === "REJECTED" && can("sales.void") && (
        <div className="sale-actions">
          <p className="small muted">Corrige el motivo del rechazo (por ejemplo, los datos del cliente) y vuelve a enviarlo con el mismo número.</p>
          <button className="primary" onClick={retry} disabled={busy}>{busy ? "Enviando…" : "Reintentar envío"}</button>
        </div>
      )}
      {error && <p className="error" role="alert">{error}</p>}
      <h3>Historial</h3>
      <ul className="plain-list">
        {doc.events.map((e, i) => (
          <li key={i}>
            <span className="muted small">{when(e.at)}</span> {EVENT_LABEL[e.kind] ?? e.kind}
            {e.detail && <span className="muted"> — {e.detail}</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}
