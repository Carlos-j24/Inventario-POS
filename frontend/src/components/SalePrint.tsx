import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

import { api, type TicketData } from "../api";
import BrandLogo from "./BrandLogo";
import { formatMoney, formatQty, toCents } from "../money";

const money = (value: string) => formatMoney(toCents(value));
const day = (iso: string) => new Date(iso).toLocaleDateString("es-CO", { day: "numeric", month: "long", year: "numeric" });
const hour = (iso: string) => new Date(iso).toLocaleTimeString("es-CO", { hour: "numeric", minute: "2-digit" });
const rateLabel = (rate: string) => (rate === "excluido" ? "Excluido" : `${rate} %`);
const km = (value: number) => `${value.toLocaleString("es-CO")} km`;

/**
 * Comprobante de venta en hoja carta (spec 013, T4), con la misma maqueta de la cotización. No es la
 * factura electrónica: lo dice arriba y abajo (decisión 6). El título es el nombre del negocio, junto al logo
 * (pedido de Arias, 2026-11-04); sin datos del negocio queda "Comprobante de venta".
 */
export default function SalePrint({ data }: { data: TicketData }) {
  const b = data.business;
  return (
    <article className="quote-sheet" aria-label="Comprobante de venta">
      <style>{"@media print { @page { size: letter portrait; margin: 14mm; } }"}</style>
      <header className="quote-sheet-head">
        <BrandLogo className="quote-sheet-logo sale-sheet-logo" alt="Logo del negocio" />
        <div className="quote-sheet-from">
          <h1 className="sale-sheet-title">{b ? b.trade_name || b.name : "Comprobante de venta"}</h1>
          {b && (
            <>
              {b.trade_name && <div>{b.name}</div>}
              {b.nit && <div>NIT {b.nit}</div>}
              {(b.address || b.city) && <div>{[b.address, b.city].filter(Boolean).join(", ")}</div>}
              {(b.phone || b.email) && <div>{[b.phone && `Tel. ${b.phone}`, b.email].filter(Boolean).join(" · ")}</div>}
            </>
          )}
        </div>
        <div className="quote-sheet-number">
          <div>Venta</div>
          <strong>{data.sale_number}</strong>
          <div>{day(data.issued_at)}, {hour(data.issued_at)}</div>
        </div>
      </header>
      <p className="quote-sheet-warning" role="note">Documento sin validez fiscal</p>

      <section className="quote-sheet-parties">
        <div>
          <span className="muted">Cliente</span>
          {data.customer ? (
            <>
              <div><strong>{data.customer.name}</strong></div>
              <div>{data.customer.document}</div>
              {data.customer.phone && <div>Tel. {data.customer.phone}</div>}
            </>
          ) : (
            <div><strong>Consumidor final</strong></div>
          )}
        </div>
        {data.work_order && (
          <div>
            <span className="muted">Moto</span>
            <div><strong>{data.work_order.plate}</strong> · {data.work_order.motorcycle}</div>
            <div>Orden {data.work_order.number} · llegó con {km(data.work_order.mileage_in)}</div>
          </div>
        )}
        <div>
          <span className="muted">Atendió</span>
          <div>{data.cashier} · {data.register}</div>
        </div>
      </section>

      <table className="quote-sheet-lines" aria-label="Productos vendidos">
        <thead>
          <tr><th className="num">Cant.</th><th>Unidad</th><th>Descripción</th><th className="num">IVA</th><th className="num">Valor unitario</th><th className="num">Total</th></tr>
        </thead>
        <tbody>
          {data.lines.map((l, i) => (
            <tr key={i}>
              <td className="num">{formatQty(l.quantity)}</td>
              <td>{l.unit}</td>
              <td>{l.name}{l.sku && <span className="muted"> ({l.sku})</span>}</td>
              <td className="num">{l.tax_rate ? rateLabel(l.tax_rate) : ""}</td>
              <td className="num">{money(l.unit_price)}</td>
              <td className="num">{money(l.total)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="quote-sheet-totals">
        <div>
          <table aria-label="IVA por tarifa">
            <thead><tr><th>Tarifa</th><th className="num">Base</th><th className="num">IVA</th></tr></thead>
            <tbody>
              {data.taxes.map((t) => (
                <tr key={t.rate}><td>{rateLabel(t.rate)}</td><td className="num">{money(t.base)}</td><td className="num">{money(t.tax)}</td></tr>
              ))}
            </tbody>
          </table>
          <table aria-label="Forma de pago">
            <thead><tr><th colSpan={2}>Pago</th></tr></thead>
            <tbody>
              {data.payments.map((p, i) => <tr key={i}><td>{p.label}</td><td className="num">{money(p.amount)}</td></tr>)}
              {toCents(data.change) > 0 && <tr><td>Vueltas</td><td className="num">{money(data.change)}</td></tr>}
            </tbody>
          </table>
        </div>
        <table aria-label="Totales">
          <tbody>
            <tr><td>Subtotal</td><td className="num">{money(data.subtotal)}</td></tr>
            <tr><td>IVA</td><td className="num">{money(data.tax)}</td></tr>
            <tr className="quote-sheet-total"><td>Total</td><td className="num">{money(data.total)}</td></tr>
          </tbody>
        </table>
      </div>

      <footer className="quote-sheet-foot">
        <p>Documento sin validez fiscal: no reemplaza la factura electrónica. Precios con IVA incluido.</p>
        {data.code && <p>Documento electrónico de esta venta: {data.title} {data.code}.</p>}
      </footer>
    </article>
  );
}

/**
 * Pide los datos de la venta y muestra el comprobante para imprimir o guardar en PDF. Va en un portal
 * directo en <body>: al imprimir se oculta todo lo demás y no salen hojas en blanco (como la cotización).
 */
export function SalePrintDialog({ saleId, onClose }: { saleId: number; onClose: () => void }) {
  const [data, setData] = useState<TicketData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let current = true;
    api<TicketData>(`/api/invoicing/ticket/${saleId}/`)
      .then((t) => current && setData(t))
      .catch((err: Error) => current && setError(err.message));
    return () => {
      current = false;
    };
  }, [saleId]);

  return createPortal(
    <div className="overlay print-portal" role="dialog" aria-label="Imprimir comprobante">
      <div className="card modal quote-modal">
        {error && <p className="error" role="alert">{error}</p>}
        {!error && !data && <p className="muted">Preparando el comprobante…</p>}
        {data && <SalePrint data={data} />}
        <div className="row no-print">
          <button type="button" className="primary" onClick={() => window.print()} disabled={!data}>Imprimir</button>
          <button type="button" onClick={onClose}>Cerrar</button>
        </div>
        <p className="muted small no-print">Para el PDF, elige "Guardar como PDF" en la impresora.</p>
      </div>
    </div>,
    document.body,
  );
}
