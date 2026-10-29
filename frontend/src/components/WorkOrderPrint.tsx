import type { Business, WorkOrderDetail } from "../api";
import { formatMoney, formatQty, toCents } from "../money";
import { describeMotorcycle, formatKm } from "../motorcycle";
import { STATUS_LABELS } from "../workOrder";
import BrandLogo from "./BrandLogo";

const money = (value: string) => formatMoney(toCents(value));
const day = (iso: string) => new Date(iso).toLocaleDateString("es-CO", { day: "numeric", month: "long", year: "numeric" });

/**
 * Hoja carta del presupuesto de una orden de trabajo (spec 011, regla 3), con el formato de la de las
 * cotizaciones (spec 007). Lo que está por aprobar va aparte para que el cliente vea qué aprueba.
 */
export default function WorkOrderPrint({ order, business }: { order: WorkOrderDetail; business: Business | null }) {
  const b = business;
  const approved = order.lines.filter((l) => l.approved && !l.returned);
  const pending = order.lines.filter((l) => !l.approved);
  const closed = order.status === "CANCELLED" ? "CANCELADA" : null;
  return (
    <article className="quote-sheet" aria-label="Hoja de la orden de trabajo">
      <style>{"@media print { @page { size: letter portrait; margin: 14mm; } }"}</style>
      <header className="quote-sheet-head">
        <BrandLogo className="quote-sheet-logo" alt="Logo del negocio" />
        <div className="quote-sheet-from">
          {b && <strong className="quote-sheet-business">{b.trade_name || b.name}</strong>}
          {b?.trade_name && <div>{b.name}</div>}
          {b?.nit && <div>NIT {b.nit}</div>}
          {b && (b.address || b.city) && <div>{[b.address, b.city].filter(Boolean).join(", ")}</div>}
          {b && (b.phone || b.email) && <div>{[b.phone && `Tel. ${b.phone}`, b.email].filter(Boolean).join(" · ")}</div>}
        </div>
        <div className="quote-sheet-number">
          <div>Orden de trabajo</div>
          <strong>{order.number}</strong>
          <div>{day(order.received_at)}</div>
          <div>{STATUS_LABELS[order.status]}</div>
        </div>
      </header>
      {closed && <p className="quote-sheet-warning" role="note">{closed}: esta orden ya no es válida.</p>}

      <section className="quote-sheet-parties">
        <div>
          <span className="muted">Cliente</span>
          <div><strong>{order.customer.name}</strong></div>
          {order.customer.phone && <div>Tel. {order.customer.phone}</div>}
        </div>
        <div>
          <span className="muted">Moto</span>
          <div><strong>{describeMotorcycle(order.motorcycle)}</strong></div>
          <div>Llegó con {formatKm(order.mileage_in)}</div>
          <span className="muted">Recibió</span>
          <div>{order.received_by}</div>
        </div>
      </section>
      <p><span className="muted">Pide:</span> {order.request}</p>
      {order.condition && <p><span className="muted">Estado al llegar:</span> {order.condition}</p>}
      {order.diagnosis && <p><span className="muted">Diagnóstico:</span> {order.diagnosis}</p>}

      {approved.length > 0 && <Lines title="Aprobado" lines={approved} total={order.charged_total} />}
      {pending.length > 0 && <Lines title="Por aprobar" lines={pending} total={order.pending_total} />}
      {order.lines.length === 0 && <p className="muted">Todavía sin repuestos ni mano de obra.</p>}

      <footer className="quote-sheet-foot">
        <p>Precios con IVA incluido. Los repuestos van al precio del día; lo que se agregue después de aprobar necesita una nueva aprobación.</p>
        <p>La moto se entrega cuando la orden esté pagada. Presente el número {order.number} en el mostrador.</p>
        <p>Aprobado por: ______________________________ Fecha: ______________</p>
      </footer>
    </article>
  );
}

function Lines({ title, lines, total }: { title: string; lines: WorkOrderDetail["lines"]; total: string }) {
  return (
    <table className="quote-sheet-lines" aria-label={title}>
      <caption>{title}</caption>
      <thead>
        <tr><th className="num">Cant.</th><th>Descripción</th><th className="num">Valor unitario</th><th className="num">Total</th></tr>
      </thead>
      <tbody>
        {lines.map((l) => (
          <tr key={l.id}>
            <td className="num">{formatQty(l.quantity)}</td>
            <td>{l.name} <span className="muted">({l.is_service ? "mano de obra" : l.sku})</span></td>
            <td className="num">{money(l.unit_price)}</td>
            <td className="num">{money(l.total)}</td>
          </tr>
        ))}
        <tr className="quote-sheet-total"><td colSpan={3}>Total {title.toLowerCase()}</td><td className="num">{money(total)}</td></tr>
      </tbody>
    </table>
  );
}
