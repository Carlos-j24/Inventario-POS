import { useEffect, useState } from "react";

import { api, type Customer } from "../api";

const ID_TYPES = [
  { id: "13", label: "Cédula" },
  { id: "31", label: "NIT" },
  { id: "22", label: "Cédula de extranjería" },
  { id: "41", label: "Pasaporte" },
  { id: "48", label: "PPT" },
];

const describe = (c: Customer) => `${c.id_type_label} ${c.id_number}${c.check_digit ? `-${c.check_digit}` : ""}`;

/**
 * Cliente del documento (spec 005, T6): consumidor final por defecto; se busca por número o
 * nombre, o se registra rápido. Sin conexión solo queda el consumidor final o el ya elegido.
 */
export default function CustomerPicker({ value, onChange, emptyLabel = "Consumidor final" }: {
  value: Customer | null;
  onChange: (c: Customer | null) => void;
  /** Lo que se muestra sin cliente elegido (en una cotización no hay "consumidor final"). */
  emptyLabel?: string;
}) {
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [q, setQ] = useState("");
  const [results, setResults] = useState<Customer[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || q.trim().length < 2) {
      setResults([]);
      return;
    }
    const timer = setTimeout(() => {
      api<Customer[]>(`/api/customers/?q=${encodeURIComponent(q.trim())}`)
        .then((rows) => { setResults(rows.filter((c) => !c.is_final_consumer)); setError(null); })
        .catch((err: Error) => setError(err.message));
    }, 250);
    return () => clearTimeout(timer);
  }, [open, q]);

  function choose(c: Customer | null) {
    onChange(c);
    setOpen(false);
    setCreating(false);
    setQ("");
  }

  if (!open) {
    return (
      <div className="row spread customer-picker">
        <span>Cliente: <strong>{value ? value.name : emptyLabel}</strong>{value && <span className="muted small"> · {describe(value)}</span>}</span>
        <span>
          <button type="button" className="link" onClick={() => setOpen(true)}>{value ? "Cambiar" : "Identificar cliente"}</button>
          {value && <button type="button" className="link" onClick={() => choose(null)}>{emptyLabel}</button>}
        </span>
      </div>
    );
  }

  return (
    <div className="card nested customer-picker">
      {creating ? (
        <NewCustomer initialNumber={/^\d+$/.test(q.trim()) ? q.trim() : ""} onCreated={choose} onCancel={() => setCreating(false)} />
      ) : (
        <>
          <input autoFocus placeholder="Número de documento o nombre" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Buscar cliente" />
          {error && <p className="error" role="alert">{error}</p>}
          <ul className="results">
            {results.map((c) => (
              <li key={c.id}>
                <button type="button" onClick={() => choose(c)}>
                  <span>{c.name}</span><span className="muted small">{describe(c)}</span>
                </button>
              </li>
            ))}
          </ul>
          <div className="row">
            <button type="button" onClick={() => setCreating(true)}>Nuevo cliente</button>
            <button type="button" className="link" onClick={() => setOpen(false)}>Cancelar</button>
          </div>
        </>
      )}
    </div>
  );
}

function NewCustomer({ initialNumber, onCreated, onCancel }: { initialNumber: string; onCreated: (c: Customer) => void; onCancel: () => void }) {
  const [idType, setIdType] = useState("13");
  const [number, setNumber] = useState(initialNumber);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [legal, setLegal] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      onCreated(await api<Customer>("/api/customers/", {
        method: "POST",
        body: { id_type: idType, id_number: number, name, email, person_type: idType === "31" && legal ? "1" : "2" },
      }));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="action-form" role="group" aria-label="Nuevo cliente">
      <div className="row">
        <select value={idType} onChange={(e) => setIdType(e.target.value)} aria-label="Tipo de documento">
          {ID_TYPES.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
        </select>
        <input value={number} onChange={(e) => setNumber(e.target.value)} placeholder="Número" aria-label="Número de documento" />
      </div>
      <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Nombre o razón social" aria-label="Nombre o razón social" />
      <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Correo (opcional)" aria-label="Correo" />
      {idType === "31" && (
        <label className="check"><input type="checkbox" checked={legal} onChange={(e) => setLegal(e.target.checked)} /> Empresa (persona jurídica)</label>
      )}
      {error && <p className="error" role="alert">{error}</p>}
      <div className="row">
        <button type="button" className="primary" onClick={save} disabled={busy || !number.trim() || !name.trim()}>Guardar cliente</button>
        <button type="button" className="link" onClick={onCancel}>Volver</button>
      </div>
    </div>
  );
}
