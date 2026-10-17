import { useEffect, useState, type ReactNode } from "react";

import {
  api,
  type InventoryReport,
  type MarginsReport,
  type PaymentMethod,
  type ProductReportRow,
  type ProductsReport,
  type Register,
  type ReportRow,
  type SalesReport,
  type ShiftsReport,
} from "../api";
import { useCan } from "../auth";
import { downloadCsv } from "../csv";
import { formatMoney, formatQty, toCents } from "../money";
import { reportCsv } from "../reportCsv";
import { formatDay, formatPct, matchPreset, PRESETS, presetPeriod, reportUrl, type Period } from "../reports";
import { todayIso } from "./Sales";

const money = (value: string) => formatMoney(toCents(value));

// Márgenes e inventario valorizado muestran costos: solo con reports.costs (spec 004, decisión 4).
const TABS: { id: string; label: string; costs?: boolean }[] = [
  { id: "sales", label: "Ventas" },
  { id: "products", label: "Productos" },
  { id: "shifts", label: "Arqueos" },
  { id: "inventory", label: "Inventario valorizado", costs: true },
  { id: "margins", label: "Márgenes", costs: true },
];

const METHODS: { id: PaymentMethod; label: string }[] = [
  { id: "CASH", label: "Efectivo" },
  { id: "CARD", label: "Tarjeta" },
  { id: "TRANSFER", label: "Transferencia" },
];

/** Spec 004: reportes por período. Los calcula el servidor; la pantalla solo los muestra. */
export default function Reports() {
  const can = useCan();
  const today = todayIso();
  const [period, setPeriod] = useState<Period>({ from: today, to: today });
  const [register, setRegister] = useState("");
  const [registers, setRegisters] = useState<Register[]>([]);
  const [tab, setTab] = useState("sales");
  const [loaded, setLoaded] = useState<{ url: string; data: unknown } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const tabs = TABS.filter((t) => !t.costs || can("reports.costs"));
  const url = reportUrl(tab, period, register);
  const preset = matchPreset(period, today);

  useEffect(() => {
    api<Register[]>("/api/cash/registers/").then(setRegisters).catch(() => setRegisters([]));
  }, []);

  useEffect(() => {
    let current = true;
    setError(null);
    api<unknown>(url)
      .then((data) => current && setLoaded({ url, data }))
      .catch((err: Error) => current && setError(err.message));
    return () => {
      current = false;
    };
  }, [url]);

  function changeFrom(from: string) {
    if (from) setPeriod((p) => ({ from, to: p.to < from ? from : p.to }));
  }

  function changeTo(to: string) {
    if (to) setPeriod((p) => ({ from: p.from > to ? to : p.from, to }));
  }

  const data = loaded?.url === url ? loaded.data : null;

  return (
    <section className="card reports">
      <h2>Reportes</h2>
      <div className="row filters">
        {PRESETS.map((p) => (
          <button
            key={p.id}
            className={p.id === preset ? "tab active" : "tab"}
            aria-pressed={p.id === preset}
            onClick={() => setPeriod(presetPeriod(p.id, today))}
          >
            {p.label}
          </button>
        ))}
        <input type="date" aria-label="Desde" value={period.from} max={today} onChange={(e) => changeFrom(e.target.value)} />
        <input type="date" aria-label="Hasta" value={period.to} max={today} onChange={(e) => changeTo(e.target.value)} />
        {registers.length > 0 && (
          <select value={register} onChange={(e) => setRegister(e.target.value)} aria-label="Caja" disabled={tab === "inventory"}>
            <option value="">Todas las cajas</option>
            {registers.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
          </select>
        )}
      </div>
      <nav className="report-tabs" aria-label="Reportes">
        {tabs.map((t) => (
          <button key={t.id} className={t.id === tab ? "tab active" : "tab"} aria-pressed={t.id === tab} onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
        <button
          className="link download"
          disabled={data == null || !!error}
          onClick={() => {
            const file = reportCsv(tab, data, period, today);
            downloadCsv(file.filename, file.content);
          }}
        >
          Descargar CSV
        </button>
      </nav>
      {error && <p className="error" role="alert">{error}</p>}
      {!error && !data && <p className="muted">Cargando…</p>}
      {!error && data != null && (
        <>
          {tab === "sales" && <SalesView report={data as SalesReport} />}
          {tab === "products" && <ProductsView report={data as ProductsReport} />}
          {tab === "shifts" && <ShiftsView report={data as ShiftsReport} />}
          {tab === "inventory" && <InventoryView report={data as InventoryReport} />}
          {tab === "margins" && <MarginsView report={data as MarginsReport} />}
        </>
      )}
    </section>
  );
}

// --- piezas comunes ---------------------------------------------------------

function Kpis({ items }: { items: [string, ReactNode][] }) {
  return (
    <dl className="kpis">
      {items.map(([label, value]) => (
        <div key={label} className="kpi">
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function Table({ title, head, children, empty }: { title: string; head: ReactNode; children: ReactNode[]; empty?: string }) {
  return (
    <div className="report-table">
      <h3>{title}</h3>
      {children.length === 0 ? (
        <p className="muted small">{empty ?? "Sin datos en el período."}</p>
      ) : (
        <div className="table-wrap">
          <table className="cart" aria-label={title}>
            <thead>{head}</thead>
            <tbody>{children}</tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function signed(value: string) {
  const cents = toCents(value);
  return <span className={cents < 0 ? "error" : cents > 0 ? "change" : undefined}>{formatMoney(cents)}</span>;
}

// --- ventas -----------------------------------------------------------------

function Breakdown<T extends ReportRow>({ title, label, rows, name }: { title: string; label: string; rows: T[]; name: (row: T) => string }) {
  return (
    <Table
      title={title}
      head={<tr><th>{label}</th><th className="num">Ventas</th><th className="num">Total</th><th className="num">Devoluciones</th><th className="num">Neto</th></tr>}
    >
      {rows.map((r) => (
        <tr key={name(r)}>
          <td>{name(r)}</td>
          <td className="num">{r.sales_count}</td>
          <td className="num">{money(r.total)}</td>
          <td className="num">{toCents(r.returns) ? money(r.returns) : "—"}</td>
          <td className="num"><strong>{money(r.net)}</strong></td>
        </tr>
      ))}
    </Table>
  );
}

function SalesView({ report }: { report: SalesReport }) {
  const t = report.totals;
  return (
    <>
      <Kpis
        items={[
          ["Venta neta", money(t.net_total)],
          ["Ventas", t.sales_count],
          ["Ticket promedio", money(t.average_ticket)],
          ["IVA neto", money(t.net_tax)],
          ["Devoluciones", money(t.returns_total)],
        ]}
      />
      <p className="muted small">
        Sin anuladas. Las devoluciones restan el día en que se hicieron. Sin IVA: {money(t.net_subtotal)}.
      </p>
      <div className="report-grid">
        <Breakdown title="Por día" label="Día" rows={report.by_day} name={(r) => formatDay(r.day)} />
        <Table
          title="Por medio de pago"
          head={<tr><th>Medio</th><th className="num">Cobros</th><th className="num">Reembolsos</th><th className="num">Neto</th></tr>}
        >
          {report.by_method.map((r) => (
            <tr key={r.method}>
              <td>{r.label}</td>
              <td className="num">{money(r.payments)}</td>
              <td className="num">{toCents(r.refunds) ? money(r.refunds) : "—"}</td>
              <td className="num"><strong>{money(r.net)}</strong></td>
            </tr>
          ))}
        </Table>
        <Breakdown title="Por caja" label="Caja" rows={report.by_register} name={(r) => r.register} />
        <Breakdown title="Por vendedor" label="Vendedor" rows={report.by_salesperson} name={(r) => r.salesperson} />
      </div>
    </>
  );
}

// --- productos --------------------------------------------------------------

function Ranking({ title, rows }: { title: string; rows: ProductReportRow[] }) {
  return (
    <Table
      title={title}
      head={<tr><th>Producto</th><th className="num">Cantidad</th><th className="num">Ventas</th><th className="num">Total</th></tr>}
    >
      {rows.map((r) => (
        <tr key={r.product}>
          <td><span className="muted small">{r.sku}</span> {r.name}</td>
          <td className="num">{formatQty(r.quantity)} {r.unit}</td>
          <td className="num">{r.sales_count}</td>
          <td className="num">{money(r.total)}</td>
        </tr>
      ))}
    </Table>
  );
}

function ProductsView({ report }: { report: ProductsReport }) {
  return (
    <div className="report-grid">
      <Ranking title="Más vendidos por cantidad" rows={report.by_quantity} />
      <Ranking title="Más vendidos por valor" rows={report.by_value} />
      <Table
        title={`Sin movimiento (${report.not_moved.length})`}
        head={<tr><th>Producto</th><th className="num">Existencias</th></tr>}
        empty="Todos los productos activos tuvieron ventas en el período."
      >
        {report.not_moved.map((r) => (
          <tr key={r.product}>
            <td><span className="muted small">{r.sku}</span> {r.name}</td>
            <td className="num">{formatQty(r.stock)} {r.unit}</td>
          </tr>
        ))}
      </Table>
    </div>
  );
}

// --- arqueos ----------------------------------------------------------------

const dateTime = (iso: string) =>
  new Date(iso).toLocaleString("es-CO", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

function ShiftsView({ report }: { report: ShiftsReport }) {
  const t = report.totals;
  return (
    <>
      <Kpis
        items={[
          ["Turnos cerrados", t.shifts],
          ["Faltantes", money(t.shortage)],
          ["Sobrantes", money(t.overage)],
          ["Diferencia neta", signed(t.difference)],
        ]}
      />
      <Table
        title="Turnos cerrados en el período"
        empty="No se cerró ningún turno en el período."
        head={
          <tr>
            <th>Caja</th><th>Cerró</th><th className="num">Ventas</th>
            {METHODS.map((m) => <th key={m.id} className="num">{m.label}</th>)}
            <th className="num">Esperado</th><th className="num">Contado</th><th className="num">Diferencia</th>
          </tr>
        }
      >
        {report.rows.map((r) => (
          <tr key={r.shift}>
            <td>{r.register}</td>
            <td>
              {r.closed_by ?? "—"} <span className="muted small">{dateTime(r.closed_at)}</span>
              {r.notes && <div className="muted small">{r.notes}</div>}
            </td>
            <td className="num">{r.sales_count}</td>
            {METHODS.map((m) => <td key={m.id} className="num">{money(r.by_method[m.id])}</td>)}
            <td className="num">{money(r.expected_cash)}</td>
            <td className="num">{money(r.counted_cash)}</td>
            <td className="num">{signed(r.difference)}</td>
          </tr>
        ))}
      </Table>
    </>
  );
}

// --- con costos -------------------------------------------------------------

function InventoryView({ report }: { report: InventoryReport }) {
  const t = report.totals;
  return (
    <>
      <Kpis
        items={[
          ["Valor del inventario", money(t.value)],
          ["Productos", t.products],
          ["Bajo el mínimo", t.below_min],
          ["En negativo", t.negative],
        ]}
      />
      <p className="muted small">Existencias de hoy × costo promedio. Una existencia en negativo vale 0.</p>
      <Table
        title="Por producto"
        head={<tr><th>Producto</th><th className="num">Existencias</th><th className="num">Costo promedio</th><th className="num">Valor</th><th /></tr>}
      >
        {report.rows.map((r) => (
          <tr key={r.product}>
            <td><span className="muted small">{r.sku}</span> {r.name}</td>
            <td className="num">{formatQty(r.stock)} {r.unit}</td>
            <td className="num">{r.average_cost == null ? "—" : money(r.average_cost)}</td>
            <td className="num">{money(r.value)}</td>
            <td>
              {r.negative && <span className="badge danger">Negativo</span>}{" "}
              {r.below_min && <span className="badge warn">Bajo el mínimo ({formatQty(r.min_stock)})</span>}
            </td>
          </tr>
        ))}
      </Table>
    </>
  );
}

function MarginsView({ report }: { report: MarginsReport }) {
  const t = report.totals;
  return (
    <>
      <Kpis
        items={[
          ["Venta neta sin IVA", money(t.net_sales)],
          ["Costo de lo vendido", money(t.cost)],
          ["Margen", signed(t.margin)],
          ["Margen %", formatPct(t.margin_pct)],
        ]}
      />
      {t.cost_estimated && (
        <p className="warn-note">
          Incluye ventas con costo estimado (anteriores al registro de costos o sin costo guardado): sus márgenes son aproximados.
        </p>
      )}
      <Table
        title="Por producto"
        head={<tr><th>Producto</th><th className="num">Venta neta</th><th className="num">Costo</th><th className="num">Margen</th><th className="num">%</th></tr>}
      >
        {report.rows.map((r) => (
          <tr key={r.product}>
            <td>
              <span className="muted small">{r.sku}</span> {r.name}
              {r.cost_estimated && <span className="badge warn" title="Costo estimado">estimado</span>}
            </td>
            <td className="num">{money(r.net_sales)}</td>
            <td className="num">{money(r.cost)}</td>
            <td className="num">{signed(r.margin)}</td>
            <td className="num">{formatPct(r.margin_pct)}</td>
          </tr>
        ))}
      </Table>
    </>
  );
}
