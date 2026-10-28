import { useMemo, useState, type FormEvent, type RefObject } from "react";

import type { Product } from "../api";
import { findByCode, searchProducts } from "../cart";
import { formatMoney, toCents } from "../money";

/** Buscador de productos: el lector de código de barras escribe el código y presiona Enter. */
export default function ProductSearch({ products, onPick, inputRef }: {
  products: Product[];
  onPick: (product: Product, unit: string) => void;
  inputRef?: RefObject<HTMLInputElement | null>;
}) {
  const [query, setQuery] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const results = useMemo(() => searchProducts(products, query), [products, query]);

  function pick(product: Product, unit = product.base_unit) {
    onPick(product, unit);
    setQuery("");
    setNotice(null);
    inputRef?.current?.focus();
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    const hit = findByCode(products, query);
    if (hit) pick(hit.product, hit.unit);
    else if (results.length === 1) pick(results[0]);
    else setNotice(results.length ? "Elige el producto de la lista." : `No se encontró "${query}".`);
  }

  return (
    <>
      <form onSubmit={submit}>
        <input
          ref={inputRef}
          className="search"
          placeholder="Código de barras, SKU o nombre…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          autoFocus
          aria-label="Buscar producto"
        />
      </form>
      {results.length > 0 && (
        <ul className="results">
          {results.map((p) => (
            <li key={p.id}>
              <button onClick={() => pick(p)}>
                <span>{p.name}</span>
                <span className="muted">{p.sku} · {formatMoney(toCents(p.sale_price))}/{p.base_unit}{p.is_service && " · servicio"}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {notice && <p className="error">{notice}</p>}
    </>
  );
}
