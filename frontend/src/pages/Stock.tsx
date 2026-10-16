import { useEffect, useMemo, useState } from "react";

import { api, type Product, type StockLevel } from "../api";
import { formatQty } from "../money";

type Filter = "all" | "low";

export default function Stock() {
  const [levels, setLevels] = useState<StockLevel[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [text, setText] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api<StockLevel[]>("/api/inventory/stock/"), api<Product[]>("/api/catalog/products/")])
      .then(([l, p]) => { setLevels(l); setProducts(p); })
      .catch((e) => setError(e.message));
  }, []);

  const bySku = useMemo(() => new Map(products.map((p) => [p.sku, p])), [products]);
  const rows = levels
    .map((l) => ({ ...l, info: bySku.get(l.product) }))
    .filter((r) => filter === "all" || r.below_min)
    .filter((r) => `${r.product} ${r.info?.name ?? ""}`.toLowerCase().includes(text.trim().toLowerCase()))
    .sort((a, b) => Number(b.below_min) - Number(a.below_min) || a.product.localeCompare(b.product));

  if (error) return <p className="error">{error}</p>;

  return (
    <section className="card">
      <div className="row spread">
        <h2>Existencias</h2>
        <div className="row">
          <input placeholder="Buscar…" value={text} onChange={(e) => setText(e.target.value)} aria-label="Buscar en existencias" />
          <select value={filter} onChange={(e) => setFilter(e.target.value as Filter)} aria-label="Filtro">
            <option value="all">Todos</option>
            <option value="low">Bajo el mínimo</option>
          </select>
        </div>
      </div>
      <table className="cart">
        <thead>
          <tr><th>SKU</th><th>Producto</th><th>Bodega</th><th className="num">Cantidad</th><th className="num">Mínimo</th><th /></tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const qty = Number(r.quantity);
            return (
              <tr key={`${r.product}-${r.warehouse}`} className={qty < 0 ? "negative" : r.below_min ? "low" : ""}>
                <td>{r.product}</td>
                <td>{r.info?.name ?? "—"}</td>
                <td>{r.warehouse}</td>
                <td className="num">{formatQty(r.quantity)} {r.info?.base_unit}</td>
                <td className="num">{r.info ? formatQty(r.info.min_stock) : "—"}</td>
                <td>{qty < 0 ? <span className="badge danger">Negativo: revisar</span> : r.below_min && <span className="badge warn">Pedir</span>}</td>
              </tr>
            );
          })}
          {rows.length === 0 && <tr><td colSpan={6} className="muted center">Sin resultados.</td></tr>}
        </tbody>
      </table>
    </section>
  );
}
