import { lineTotalCents, quantityError, unitPriceCents, type CartLine } from "../cart";
import { formatMoney, formatQty } from "../money";

/** Tabla editable del carrito (cantidad, unidad, quitar), compartida por la caja y los pedidos. */
export default function CartTable({ lines, onChange, emptyText }: {
  lines: CartLine[];
  onChange: (lines: CartLine[]) => void;
  emptyText: string;
}) {
  const update = (key: string, patch: Partial<CartLine>) =>
    onChange(lines.map((l) => (l.key === key ? { ...l, ...patch } : l)));

  return (
    <table className="cart">
      <thead>
        <tr><th>Producto</th><th>Cantidad</th><th>Unidad</th><th className="num">Precio</th><th className="num">Total</th><th /></tr>
      </thead>
      <tbody>
        {lines.map((l) => {
          const error = quantityError(l);
          return (
            <tr key={l.key}>
              <td>{l.product.name}{error && <div className="error small">{error}</div>}</td>
              <td>
                <input
                  className="qty"
                  type="number"
                  min="0"
                  step={l.product.allows_fractions ? "0.001" : "1"}
                  value={l.quantity}
                  onChange={(e) => update(l.key, { quantity: Number(e.target.value) })}
                  aria-label={`Cantidad de ${l.product.name}`}
                />
              </td>
              <td>
                <select value={l.unit} onChange={(e) => update(l.key, { unit: e.target.value })} aria-label={`Unidad de ${l.product.name}`}>
                  <option value={l.product.base_unit}>{l.product.base_unit}</option>
                  {l.product.units.map((u) => (
                    <option key={u.unit} value={u.unit}>{u.unit} ({formatQty(u.factor)} {l.product.base_unit})</option>
                  ))}
                </select>
              </td>
              <td className="num">{formatMoney(unitPriceCents(l.product, l.unit))}</td>
              <td className="num">{formatMoney(lineTotalCents(l))}</td>
              <td>
                <button className="link" onClick={() => onChange(lines.filter((x) => x.key !== l.key))} aria-label={`Quitar ${l.product.name}`}>
                  ✕
                </button>
              </td>
            </tr>
          );
        })}
        {lines.length === 0 && (
          <tr><td colSpan={6} className="muted center">{emptyText}</td></tr>
        )}
      </tbody>
    </table>
  );
}
