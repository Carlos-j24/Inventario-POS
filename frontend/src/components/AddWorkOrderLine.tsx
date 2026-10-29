import { useEffect, useState, type FormEvent } from "react";

import { api, type Product } from "../api";
import { formatMoney, toCents } from "../money";
import ProductSearch from "./ProductSearch";

const money = (value: string) => formatMoney(toCents(value));

/**
 * Agrega un repuesto (al precio del catálogo) o mano de obra a una orden (spec 011). Recepción puede ponerle
 * precio a la mano de obra (`canPrice`); el mecánico no: queda al precio del catálogo y recepción lo cambia.
 */
export default function AddWorkOrderLine({ onAdd, canPrice = false }: {
  onAdd: (body: Record<string, string>, name: string) => Promise<boolean>;
  canPrice?: boolean;
}) {
  const [products, setProducts] = useState<Product[]>([]);
  const [picked, setPicked] = useState<Product | null>(null);
  const [quantity, setQuantity] = useState("1");
  const [price, setPrice] = useState("");
  useEffect(() => { api<Product[]>("/api/catalog/products/").then(setProducts).catch(() => setProducts([])); }, []);

  const validQty = /^\d+([.,]\d+)?$/.test(quantity.trim()) && Number(quantity.replace(",", ".")) > 0;
  const validPrice = !price.trim() || /^\d+$/.test(price.trim());

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!picked || !validQty || !validPrice) return;
    const body: Record<string, string> = { product: String(picked.id), quantity: quantity.trim().replace(",", ".") };
    if (picked.is_service && price.trim()) body.unit_price = price.trim();
    if (await onAdd(body, picked.name)) { setPicked(null); setQuantity("1"); setPrice(""); }
  }

  if (!picked) {
    return (
      <div className="action-form" aria-label="Agregar al presupuesto">
        <ProductSearch products={products} onPick={(p) => setPicked(p)} />
      </div>
    );
  }
  return (
    <form className="action-form" onSubmit={submit} aria-label="Agregar al presupuesto">
      <p>
        <strong>{picked.name}</strong> <span className="muted small">
          {picked.is_service ? "mano de obra" : `${picked.sku} · ${money(picked.sale_price)} c/u (precio del catálogo)`}</span>
      </p>
      <div className="row">
        <label>Cantidad<input inputMode="decimal" value={quantity} onChange={(e) => setQuantity(e.target.value)} size={5} /></label>
        {canPrice && picked.is_service && (
          <label>Precio de este trabajo<input inputMode="numeric" value={price} onChange={(e) => setPrice(e.target.value)} placeholder={String(toCents(picked.sale_price) / 100)} /></label>
        )}
      </div>
      <div className="row">
        <button type="button" onClick={() => setPicked(null)}>Cancelar</button>
        <button className="primary" disabled={!validQty || !validPrice}>Agregar</button>
      </div>
    </form>
  );
}
