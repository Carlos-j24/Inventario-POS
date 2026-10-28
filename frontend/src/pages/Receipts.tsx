import { useEffect, useMemo, useState, type FormEvent } from "react";

import { api, type Product, type StockMovement } from "../api";
import { searchProducts, stockedProducts } from "../cart";
import { centsToApi, formatQty, toCents } from "../money";
import { useWarehouseChoice } from "../useWarehouseChoice";

interface Done {
  product: Product;
  quantity: string;
  unit: string;
  balance: string;
}

export default function Receipts() {
  const [products, setProducts] = useState<Product[]>([]);
  const [query, setQuery] = useState("");
  const [product, setProduct] = useState<Product | null>(null);
  const [unit, setUnit] = useState("");
  const [quantity, setQuantity] = useState("");
  const [cost, setCost] = useState("");
  const [reference, setReference] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<Done[]>([]);
  const [clientUuid, setClientUuid] = useState(() => crypto.randomUUID());
  const { warehouses, warehouse: warehouseId, choose: setWarehouseId } = useWarehouseChoice(setError);

  useEffect(() => {
    api<Product[]>("/api/catalog/products/").then((p) => setProducts(stockedProducts(p))).catch((e) => setError(e.message));
  }, []);

  const results = useMemo(() => (product ? [] : searchProducts(products, query)), [products, query, product]);

  function choose(p: Product) {
    setProduct(p);
    setUnit(p.units[0]?.unit ?? p.base_unit); // se suele comprar por presentación (rollo, caja)
    setQuery(p.name);
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!product || !warehouseId) return;
    setError(null);
    try {
      const mov = await api<StockMovement>("/api/inventory/receipts/", {
        method: "POST",
        body: {
          client_uuid: clientUuid,
          product: product.id,
          warehouse: warehouseId,
          quantity,
          unit,
          unit_cost: centsToApi(toCents(cost)),
          reference,
        },
      });
      setDone([{ product, quantity, unit, balance: mov.balance_after }, ...done]);
      setProduct(null);
      setQuery("");
      setQuantity("");
      setCost("");
      setClientUuid(crypto.randomUUID());
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <div className="two-cols">
      <form className="card" onSubmit={submit}>
        <h2>Entrada a bodega</h2>
        <label>
          Bodega
          <select value={warehouseId ?? ""} onChange={(e) => setWarehouseId(Number(e.target.value))}>
            {warehouses.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
          </select>
        </label>
        <label>
          Producto
          <input
            value={query}
            onChange={(e) => { setQuery(e.target.value); setProduct(null); }}
            placeholder="SKU o nombre…"
            autoFocus
          />
        </label>
        {results.length > 0 && (
          <ul className="results">
            {results.map((p) => (
              <li key={p.id}><button type="button" onClick={() => choose(p)}>{p.name} <span className="muted">{p.sku}</span></button></li>
            ))}
          </ul>
        )}
        {product && (
          <>
            <div className="row">
              <label>
                Cantidad
                <input inputMode="decimal" value={quantity} onChange={(e) => setQuantity(e.target.value)} />
              </label>
              <label>
                Unidad
                <select value={unit} onChange={(e) => setUnit(e.target.value)}>
                  <option value={product.base_unit}>{product.base_unit}</option>
                  {product.units.map((u) => (
                    <option key={u.unit} value={u.unit}>{u.unit} ({formatQty(u.factor)} {product.base_unit})</option>
                  ))}
                </select>
              </label>
            </div>
            <label>
              Costo por {unit}
              <input inputMode="decimal" value={cost} onChange={(e) => setCost(e.target.value)} placeholder="0" />
            </label>
            <label>
              Factura o remisión
              <input value={reference} onChange={(e) => setReference(e.target.value)} placeholder="FAC-1043" />
            </label>
          </>
        )}
        {error && <p className="error" role="alert">{error}</p>}
        <button className="primary" disabled={!product || !quantity || !cost}>Registrar entrada</button>
      </form>

      <section className="card">
        <h2>Registradas en esta sesión</h2>
        {done.length === 0 && <p className="muted">Todavía ninguna.</p>}
        <ul className="plain-list">
          {done.map((d, i) => (
            <li key={i}>
              <strong>{d.product.name}</strong>: +{formatQty(d.quantity)} {d.unit}
              <span className="muted"> · queda {formatQty(d.balance)} {d.product.base_unit}</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
