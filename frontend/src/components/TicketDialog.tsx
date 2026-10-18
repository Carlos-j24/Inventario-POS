import { useEffect, useState } from "react";

import { api, type TicketData } from "../api";
import Ticket from "./Ticket";

/**
 * Muestra e imprime el tiquete. Con saleId lo pide al servidor; si el documento sigue pendiente,
 * lo envía primero para entregarlo validado (spec 005, T6). Con data, imprime el que armó el POS
 * sin conexión.
 */
export default function TicketDialog({ saleId, data, onClose }: { saleId?: number; data?: TicketData; onClose: () => void }) {
  const [ticket, setTicket] = useState<TicketData | null>(data ?? null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (saleId == null) return;
    let current = true;
    (async () => {
      let t = await api<TicketData>(`/api/invoicing/ticket/${saleId}/`);
      if (t.status === "PENDING" && t.document_id) {
        await api(`/api/invoicing/documents/${t.document_id}/send/`, { method: "POST" }).catch(() => null);
        t = await api<TicketData>(`/api/invoicing/ticket/${saleId}/`);
      }
      if (current) setTicket(t);
    })().catch((err: Error) => current && setError(err.message));
    return () => {
      current = false;
    };
  }, [saleId]);

  return (
    <div className="overlay ticket-overlay" role="dialog" aria-label="Tiquete de venta">
      <div className="card modal">
        {error && <p className="error" role="alert">{error}</p>}
        {!error && !ticket && <p className="muted">Preparando el tiquete…</p>}
        {ticket && <Ticket data={ticket} />}
        <div className="row no-print">
          <button className="primary" onClick={() => window.print()} disabled={!ticket}>Imprimir</button>
          <button onClick={onClose}>Cerrar</button>
        </div>
      </div>
    </div>
  );
}
