import { useCallback, useEffect, useState, type FormEvent } from "react";

import { api, type AdminProduct, type Category, type PriceChange, type UnitOption } from "../api";
import { useCan } from "../auth";
import { formatMoney, formatQty, toCents } from "../money";
import { EMPTY_FORM, productPayload, toForm, type ProductForm } from "../productForm";

const URL = "/api/catalog/admin/products/";

export function productsQuery(q: string, category: string, active: string): string {
  const params = new URLSearchParams();
  if (q.trim()) params.set("q", q.trim());
  if (category) params.set("category", category);
  if (active) params.set("active", active);
  const s = params.toString();
  return `${URL}${s ? `?${s}` : ""}`;
}

/** Spec 006, T2: productos, precios, presentaciones y códigos de barras desde la app. */
export default function Products() {
  const [q, setQ] = useState("");
  const [category, setCategory] = useState("");
  const [active, setActive] = useState("");
  const [rows, setRows] = useState<AdminProduct[] | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [units, setUnits] = useState<UnitOption[]>([]);
  const [selected, setSelected] = useState<number | "new" | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Aviso al crear: va aquí porque el formulario se cambia por el del producto nuevo.
  const [notice, setNotice] = useState<string | null>(null);
  const select = (id: number | "new" | null) => { setNotice(null); setSelected(id); };

  const load = useCallback(() => {
    api<AdminProduct[]>(productsQuery(q, category, active)).then(setRows).catch((e: Error) => setError(e.message));
  }, [q, category, active]);
  const loadCategories = useCallback(() => api<Category[]>("/api/catalog/categories/").then(setCategories).catch(() => {}), []);

  useEffect(() => {
    const timer = setTimeout(load, 250); // al escribir, espera a que termine
    return () => clearTimeout(timer);
  }, [load]);
  useEffect(() => {
    loadCategories();
    api<UnitOption[]>("/api/catalog/units/").then(setUnits).catch(() => {});
  }, [loadCategories]);

  const current = typeof selected === "number" ? rows?.find((p) => p.id === selected) : undefined;

  return (
    <div className="two-cols sales-page">
      <section className="card">
        <div className="row spread">
          <h2>Productos</h2>
          <button className="primary" onClick={() => select("new")}>Nuevo producto</button>
        </div>
        <div className="row filters">
          <input placeholder="SKU, nombre o código de barras" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Buscar producto" />
          <select value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Categoría">
            <option value="">Todas las categorías</option>
            {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          <select value={active} onChange={(e) => setActive(e.target.value)} aria-label="Estado">
            <option value="">Activos e inactivos</option>
            <option value="1">Activos</option>
            <option value="0">Inactivos</option>
          </select>
        </div>
        {error && <p className="error" role="alert">{error}</p>}
        <div className="table-wrap">
          <table className="cart sales-list" aria-label="Productos">
            <thead><tr><th>SKU</th><th>Producto</th><th>Categoría</th><th className="num">Precio</th><th /></tr></thead>
            <tbody>
              {(rows ?? []).map((p) => (
                <tr key={p.id} className={p.id === selected ? "selected" : !p.is_active ? "voided" : ""} onClick={() => select(p.id)}>
                  <td><button className="link" onClick={() => select(p.id)}>{p.sku}</button></td>
                  <td>{p.name}</td>
                  <td>{p.category_name}</td>
                  <td className="num">{p.price_pending ? "—" : formatMoney(toCents(p.sale_price))}</td>
                  <td>
                    <span className="row badges">
                      {p.price_pending && <span className="badge warn">Pendiente de precio</span>}
                      {!p.is_active && !p.price_pending && <span className="badge danger">Inactivo</span>}
                    </span>
                  </td>
                </tr>
              ))}
              {rows && rows.length === 0 && <tr><td colSpan={5} className="muted center">Ningún producto.</td></tr>}
            </tbody>
          </table>
        </div>
        {rows && rows.length === 200 && <p className="muted small">Se muestran los primeros 200: afina la búsqueda.</p>}
      </section>
      <aside className="card">
        {notice && <p className="change" role="status">{notice}</p>}
        {selected === "new" && (
          <ProductEditor
            key="new" product={null} categories={categories} units={units} onCategoriesChanged={loadCategories}
            onSaved={(p) => {
              load();
              setSelected(p.id);
              setNotice(p.price_pending
                ? "Producto creado. Queda inactivo hasta que alguien con permiso de precios le ponga precio."
                : "Producto creado.");
            }}
            onCancel={() => select(null)}
          />
        )}
        {current && (
          <ProductEditor
            key={current.id} product={current} categories={categories} units={units} onCategoriesChanged={loadCategories}
            onSaved={() => load()} onCancel={() => select(null)}
          />
        )}
        {selected === null && <p className="muted">Elige un producto o crea uno nuevo.</p>}
      </aside>
    </div>
  );
}

function ProductEditor({ product, categories, units, onCategoriesChanged, onSaved, onCancel }: {
  product: AdminProduct | null;
  categories: Category[];
  units: UnitOption[];
  onCategoriesChanged: () => void;
  onSaved: (p: AdminProduct) => void;
  onCancel: () => void;
}) {
  const can = useCan();
  const canPrice = can("catalog.edit_prices");
  const [form, setForm] = useState<ProductForm>(product ? toForm(product) : EMPTY_FORM);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [newCategory, setNewCategory] = useState<string | null>(null);
  const set = <K extends keyof ProductForm>(key: K, value: ProductForm[K]) => setForm({ ...form, [key]: value });
  const locked = product?.has_movements ?? false;

  async function save(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setMessage(null);
    const result = productPayload(form, product, canPrice);
    if ("error" in result) return setError(result.error);
    if (product && Object.keys(result.body).length === 0) return setMessage("No hay cambios.");
    try {
      const saved = await api<AdminProduct>(product ? `${URL}${product.id}/` : URL, { method: product ? "PATCH" : "POST", body: result.body });
      if (product) setMessage("Cambios guardados.");
      onSaved(saved);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function addCategory() {
    if (!newCategory?.trim()) return;
    try {
      const c = await api<Category>("/api/catalog/categories/", { method: "POST", body: { name: newCategory } });
      onCategoriesChanged();
      setForm({ ...form, category: String(c.id) });
      setNewCategory(null);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <div className="action-form">
      <form className="action-form" onSubmit={save} aria-label="Producto">
        <h2>{product ? product.name : "Nuevo producto"}</h2>
        {product?.price_pending && (
          <p className="warn-note">Pendiente de precio: no se vende hasta que alguien con permiso de precios se lo ponga.</p>
        )}
        <div className="row">
          <label>SKU<input value={form.sku} onChange={(e) => set("sku", e.target.value)} disabled={locked} required /></label>
          <label>Código de barras<input value={form.barcode} onChange={(e) => set("barcode", e.target.value)} /></label>
        </div>
        {locked && <p className="muted small">Tiene movimientos: el SKU y la unidad base ya no cambian.</p>}
        <label>Nombre<input value={form.name} onChange={(e) => set("name", e.target.value)} required /></label>
        <div className="row">
          <label>
            Categoría
            <select value={form.category} onChange={(e) => set("category", e.target.value)} required>
              <option value="">Elige…</option>
              {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </label>
          <label>
            Unidad base
            <select value={form.base_unit} onChange={(e) => set("base_unit", e.target.value)} disabled={locked}>
              {units.map((u) => <option key={u.code} value={u.code}>{u.name} ({u.code})</option>)}
            </select>
          </label>
        </div>
        {newCategory === null ? (
          <button type="button" className="link" onClick={() => setNewCategory("")}>Nueva categoría</button>
        ) : (
          <div className="row">
            <input value={newCategory} onChange={(e) => setNewCategory(e.target.value)} placeholder="Nombre de la categoría" aria-label="Nueva categoría" />
            <button type="button" onClick={addCategory}>Crear</button>
            <button type="button" className="link" onClick={() => setNewCategory(null)}>Cancelar</button>
          </div>
        )}
        <div className="row">
          <label>
            Precio de venta (IVA incluido)
            <input value={form.price} onChange={(e) => set("price", e.target.value)} disabled={!canPrice} inputMode="decimal"
              placeholder={canPrice ? "12500" : "Lo pone quien tiene permiso de precios"} />
          </label>
          <label>
            IVA
            <select value={form.tax_rate} onChange={(e) => set("tax_rate", e.target.value as ProductForm["tax_rate"])} disabled={!canPrice}>
              <option value="19">19 %</option>
              <option value="5">5 %</option>
              <option value="0">0 %</option>
            </select>
          </label>
        </div>
        <label className="check">
          <input type="checkbox" checked={form.vat_excluded} onChange={(e) => set("vat_excluded", e.target.checked)} disabled={!canPrice || form.tax_rate !== "0"} />
          Excluido de IVA (no causa IVA; distinto de exento)
        </label>
        <div className="row">
          <label>Stock mínimo ({form.base_unit})<input value={form.min_stock} onChange={(e) => set("min_stock", e.target.value)} inputMode="decimal" /></label>
          <label className="check"><input type="checkbox" checked={form.allows_fractions} onChange={(e) => set("allows_fractions", e.target.checked)} /> Se vende fraccionado</label>
        </div>
        <label className="check">
          <input type="checkbox" checked={form.is_active} onChange={(e) => set("is_active", e.target.checked)} /> Activo (se vende en la caja)
        </label>
        {message && <p className="change" role="status">{message}</p>}
        {error && <p className="error" role="alert">{error}</p>}
        <div className="row">
          <button type="button" onClick={onCancel}>Cerrar</button>
          <button className="primary">{product ? "Guardar cambios" : "Crear producto"}</button>
        </div>
      </form>
      {product && <Presentations product={product} units={units} onChanged={() => onSaved(product)} />}
      {product && <PriceHistory productId={product.id} key={product.sale_price} />}
    </div>
  );
}

function Presentations({ product, units, onChanged }: { product: AdminProduct; units: UnitOption[]; onChanged: () => void }) {
  const [unit, setUnit] = useState("");
  const [factor, setFactor] = useState("");
  const [barcode, setBarcode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const available = units.filter((u) => u.code !== product.base_unit && !product.units.some((p) => p.unit === u.code));

  async function run(call: Promise<unknown>) {
    setError(null);
    try {
      await call;
      onChanged();
      return true;
    } catch (err) {
      setError((err as Error).message);
      return false;
    }
  }

  async function add() {
    const ok = await run(api(`${URL}${product.id}/units/`, { method: "POST", body: { unit, factor, barcode: barcode.trim() || null } }));
    if (ok) { setUnit(""); setFactor(""); setBarcode(""); }
  }

  return (
    <section aria-label="Presentaciones">
      <h3>Presentaciones</h3>
      {product.units.length === 0 && <p className="muted small">Solo se vende por {product.base_unit}.</p>}
      <ul className="plain-list">
        {product.units.map((p) => (
          <li key={p.id} className={p.is_active ? "" : "muted"}>
            1 {p.unit} = {formatQty(p.factor)} {product.base_unit}{p.barcode && <span className="muted small"> · {p.barcode}</span>}
            {!p.is_active && <span className="badge"> inactiva</span>}{" "}
            <button className="link" onClick={() => run(api(`/api/catalog/admin/units/${p.id}/`, { method: "PATCH", body: { is_active: !p.is_active } }))}>
              {p.is_active ? "Desactivar" : "Activar"}
            </button>
            {!p.in_use && (
              <button className="link" onClick={() => run(api(`/api/catalog/admin/units/${p.id}/`, { method: "DELETE" }))}>Borrar</button>
            )}
          </li>
        ))}
      </ul>
      {available.length > 0 && (
        <div className="row">
          <select value={unit} onChange={(e) => setUnit(e.target.value)} aria-label="Unidad de la presentación">
            <option value="">Unidad…</option>
            {available.map((u) => <option key={u.code} value={u.code}>{u.name} ({u.code})</option>)}
          </select>
          <input value={factor} onChange={(e) => setFactor(e.target.value)} placeholder={`Cuántos ${product.base_unit}`} aria-label="Factor" inputMode="decimal" />
          <input value={barcode} onChange={(e) => setBarcode(e.target.value)} placeholder="Código (opcional)" aria-label="Código de la presentación" />
          <button type="button" onClick={add} disabled={!unit || !(Number(factor) > 0)}>Agregar</button>
        </div>
      )}
      <p className="muted small">Una presentación ya vendida no cambia de factor: desactívala y crea otra con otra unidad.</p>
      {error && <p className="error" role="alert">{error}</p>}
    </section>
  );
}

function PriceHistory({ productId }: { productId: number }) {
  const [rows, setRows] = useState<PriceChange[] | null>(null);
  useEffect(() => {
    api<PriceChange[]>(`${URL}${productId}/price-history/`).then(setRows).catch(() => setRows([]));
  }, [productId]);
  if (!rows || rows.length === 0) return null;
  return (
    <section aria-label="Historial de precios">
      <h3>Historial de precios</h3>
      <ul className="plain-list">
        {rows.map((r, i) => (
          <li key={i}>
            <span className="muted small">{new Date(r.at).toLocaleString("es-CO")} · {r.user}</span>{" "}
            {r.old_price == null ? "precio inicial" : formatMoney(toCents(r.old_price))} → <strong>{formatMoney(toCents(r.new_price))}</strong>
          </li>
        ))}
      </ul>
    </section>
  );
}
