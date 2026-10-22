import type { QuoteDetail } from "../api";
import { formatMoney, formatQty, toCents } from "../money";

const money = (value: string) => formatMoney(toCents(value));
const day = (iso: string) => new Date(iso.length === 10 ? `${iso}T12:00:00` : iso).toLocaleDateString("es-CO", { day: "numeric", month: "long", year: "numeric" });
const rateLabel = (rate: string) => (rate === "excluido" ? "Excluido" : `${rate} %`);

/**
 * Hoja carta de la cotización para el cliente (spec 007, T5). "Guardar como PDF" lo hace el navegador.
 * Mientras está en pantalla, su @page (carta) gana sobre la del tiquete de 80 mm porque va después.
 */
export default function QuotePrint({ quote }: { quote: QuoteDetail }) {
  const b = quote.business;
  const warning = quote.status === "VOIDED" ? "ANULADA" : quote.status === "EXPIRED" ? "VENCIDA" : null;
  return (
    <article className="quote-sheet" aria-label="Hoja de la cotización">
      <style>{"@media print { @page { size: letter portrait; margin: 14mm; } }"}</style>
      <header className="quote-sheet-head">
        <div>
          <strong className="quote-sheet-business">{b.trade_name || b.name}</strong>
          {b.trade_name && <div>{b.name}</div>}
          {b.nit && <div>NIT {b.nit}</div>}
          {(b.address || b.city) && <div>{[b.address, b.city].filter(Boolean).join(", ")}</div>}
          {(b.phone || b.email) && <div>{[b.phone && `Tel. ${b.phone}`, b.email].filter(Boolean).join(" · ")}</div>}
        </div>
        <div className="quote-sheet-number">
          <div>Cotización</div>
          <strong>{quote.number}</strong>
          <div>{day(quote.created_at)}</div>
        </div>
      </header>
      {warning && <p className="quote-sheet-warning" role="note">{warning}: esta cotización ya no es válida.</p>}

      <section className="quote-sheet-parties">
        <div>
          <span className="muted">Cliente</span>
          <div><strong>{quote.customer}</strong></div>
          {quote.customer_document && <div>{quote.customer_document}</div>}
          {quote.customer_phone && <div>Tel. {quote.customer_phone}</div>}
        </div>
        <div>
          <span className="muted">Válida hasta</span>
          <div><strong>{day(quote.valid_until)}</strong></div>
          <span className="muted">Atendió</span>
          <div>{quote.created_by}</div>
        </div>
      </section>
      {quote.note && <p><span className="muted">Nota:</span> {quote.note}</p>}

      <table className="quote-sheet-lines" aria-label="Productos cotizados">
        <thead>
          <tr><th className="num">Cant.</th><th>Unidad</th><th>Descripción</th><th className="num">IVA</th><th className="num">Valor unitario</th><th className="num">Total</th></tr>
        </thead>
        <tbody>
          {quote.lines.map((l) => (
            <tr key={l.id}>
              <td className="num">{formatQty(l.quantity)}</td>
              <td>{l.unit}</td>
              <td>{l.name} <span className="muted">({l.sku})</span></td>
              <td className="num">{rateLabel(l.vat_excluded ? "excluido" : l.tax_rate)}</td>
              <td className="num">{money(l.unit_price)}</td>
              <td className="num">{money(l.total)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="quote-sheet-totals">
        <table aria-label="IVA por tarifa">
          <thead><tr><th>Tarifa</th><th className="num">Base</th><th className="num">IVA</th></tr></thead>
          <tbody>
            {quote.taxes.map((t) => (
              <tr key={t.rate}><td>{rateLabel(t.rate)}</td><td className="num">{money(t.base)}</td><td className="num">{money(t.tax)}</td></tr>
            ))}
          </tbody>
        </table>
        <table aria-label="Totales">
          <tbody>
            <tr><td>Subtotal</td><td className="num">{money(quote.subtotal)}</td></tr>
            <tr><td>IVA</td><td className="num">{money(quote.tax)}</td></tr>
            <tr className="quote-sheet-total"><td>Total</td><td className="num">{money(quote.total)}</td></tr>
          </tbody>
        </table>
      </div>

      <footer className="quote-sheet-foot">
        <p>Precios con IVA incluido, válidos hasta el {day(quote.valid_until)}. Sujeto a disponibilidad de existencias.</p>
        <p>Esta cotización no es una factura. Para comprar, presente el número {quote.number} en el mostrador.</p>
      </footer>
    </article>
  );
}
