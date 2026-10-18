import type { TicketData } from "../api";
import { formatMoney, formatQty, toCents } from "../money";

const money = (value: string) => formatMoney(toCents(value));
const when = (iso: string) => new Date(iso).toLocaleString("es-CO", { dateStyle: "short", timeStyle: "short" });

/** Tiquete de 80 mm (Res. 165 de 2023, art. 19). Al imprimir, solo sale esto (ver styles.css). */
export default function Ticket({ data }: { data: TicketData }) {
  const b = data.business;
  return (
    <article className="ticket" aria-label="Tiquete">
      {b && (
        <header className="ticket-center">
          <strong>{b.name}</strong>
          {b.trade_name && <div>{b.trade_name}</div>}
          {b.nit && <div>NIT {b.nit}</div>}
          {b.tax_regime && <div>{b.tax_regime}</div>}
          {(b.address || b.city) && <div>{[b.address, b.city].filter(Boolean).join(", ")}</div>}
          {b.phone && <div>Tel. {b.phone}</div>}
        </header>
      )}
      <div className="ticket-center ticket-title">
        <strong>{data.title}</strong>
        {data.code && <div className="ticket-code">{data.code}</div>}
      </div>
      <div>{when(data.issued_at)} · Caja {data.register} · {data.cashier}</div>
      {data.sale_number && <div>Venta {data.sale_number}</div>}
      <div>Cliente: {data.customer ? `${data.customer.name} · ${data.customer.document}` : "Consumidor final"}</div>
      <table className="ticket-lines">
        <tbody>
          {data.lines.map((l, i) => (
            <tr key={i}>
              <td>{formatQty(l.quantity)} {l.unit} {l.name} <span className="ticket-muted">× {money(l.unit_price)}</span></td>
              <td className="num">{money(l.total)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <table className="ticket-totals">
        <tbody>
          {data.taxes.map((t) => (
            <tr key={t.rate}>
              <td>{t.rate === "excluido" ? "Excluido de IVA" : `Base IVA ${t.rate} %`} {money(t.base)}</td>
              <td className="num">IVA {money(t.tax)}</td>
            </tr>
          ))}
          <tr className="ticket-total"><td>Total</td><td className="num">{money(data.total)}</td></tr>
          {data.payments.map((p, i) => <tr key={i}><td>{p.label}</td><td className="num">{money(p.amount)}</td></tr>)}
          {toCents(data.change) > 0 && <tr><td>Vueltas</td><td className="num">{money(data.change)}</td></tr>}
        </tbody>
      </table>
      {data.qr_svg && <div className="ticket-center ticket-qr" dangerouslySetInnerHTML={{ __html: data.qr_svg }} />}
      {data.cude && <div className="ticket-cude">CUDE: {data.cude}</div>}
      {data.notes.map((n) => <div key={n} className="ticket-center ticket-note">{n}</div>)}
      {data.resolution && <div className="ticket-muted">{data.resolution}</div>}
    </article>
  );
}
