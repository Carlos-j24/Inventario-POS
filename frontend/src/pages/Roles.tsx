import { useCallback, useEffect, useState, type FormEvent } from "react";

import { api, type PermissionInfo, type Role } from "../api";

/** Grupos para leer los permisos por tema (el prefijo del código). */
const GROUPS: Record<string, string> = {
  users: "Usuarios",
  catalog: "Catálogo",
  inventory: "Inventario",
  sales: "Ventas",
  cash: "Caja",
  reports: "Reportes",
  workshop: "Taller",
};

export function groupPermissions(perms: PermissionInfo[]): { group: string; items: PermissionInfo[] }[] {
  const by = new Map<string, PermissionInfo[]>();
  for (const p of perms) {
    const group = GROUPS[p.code.split(".")[0]] ?? "Otros";
    by.set(group, [...(by.get(group) ?? []), p]);
  }
  return [...by.entries()].map(([group, items]) => ({ group, items }));
}

/** Spec 003, T6: roles editables, también los que vienen por defecto (decisión 4). */
export default function Roles() {
  const [roles, setRoles] = useState<Role[] | null>(null);
  const [perms, setPerms] = useState<PermissionInfo[]>([]);
  const [selected, setSelected] = useState<number | "new" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => api<Role[]>("/api/accounts/roles/").then(setRoles).catch((e) => setError(e.message)), []);
  useEffect(() => {
    load();
    api<PermissionInfo[]>("/api/accounts/permissions/").then(setPerms).catch((e) => setError(e.message));
  }, [load]);

  const role = typeof selected === "number" ? roles?.find((r) => r.id === selected) : undefined;

  return (
    <div className="two-cols">
      <section className="card">
        <div className="row spread">
          <h2>Roles</h2>
          <button className="primary" onClick={() => setSelected("new")}>Nuevo rol</button>
        </div>
        {error && <p className="error" role="alert">{error}</p>}
        <ul className="results">
          {roles?.map((r) => (
            <li key={r.id}>
              <button onClick={() => setSelected(r.id)} className={r.id === selected ? "active-item" : ""}>
                <span>{r.name}</span>
                <span className="muted">{r.permissions.length} permiso(s)</span>
              </button>
            </li>
          ))}
        </ul>
      </section>
      <aside className="card">
        {selected === "new" && (
          <RoleForm perms={perms} onSaved={(r) => { load(); setSelected(r.id); }} onCancel={() => setSelected(null)} />
        )}
        {role && <RoleForm key={role.id} role={role} perms={perms} onSaved={() => load()} />}
        {selected === null && <p className="muted">Elige un rol para ver y cambiar sus permisos.</p>}
      </aside>
    </div>
  );
}

function RoleForm({ role, perms, onSaved, onCancel }: {
  role?: Role;
  perms: PermissionInfo[];
  onSaved: (r: Role) => void;
  onCancel?: () => void;
}) {
  const [name, setName] = useState(role?.name ?? "");
  const [codes, setCodes] = useState<string[]>(role?.permissions ?? []);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const changed = !role || name !== role.name || [...codes].sort().join() !== [...role.permissions].sort().join();

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setMessage(null);
    try {
      const saved = await api<Role>(role ? `/api/accounts/roles/${role.id}/` : "/api/accounts/roles/", {
        method: role ? "PATCH" : "POST",
        body: { name, permissions: codes },
      });
      // El servidor aplica los permisos al instante; las pantallas de cada usuario cambian al recargar la app.
      setMessage(role ? "Rol guardado. Sus usuarios verán el cambio al recargar la app." : "Rol creado.");
      onSaved(saved);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <form className="action-form" onSubmit={submit}>
      <h2>{role ? role.name : "Nuevo rol"}</h2>
      <label>
        Nombre
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Comprador" />
      </label>
      {groupPermissions(perms).map(({ group, items }) => (
        <fieldset key={group} className="role-checks perm-group">
          <legend>{group}</legend>
          {items.map((p) => (
            <label key={p.code} className="check">
              <input
                type="checkbox"
                checked={codes.includes(p.code)}
                onChange={(e) => setCodes(e.target.checked ? [...codes, p.code] : codes.filter((c) => c !== p.code))}
              />
              {p.description}
            </label>
          ))}
        </fieldset>
      ))}
      {error && <p className="error" role="alert">{error}</p>}
      {message && <p className="change" role="status">{message}</p>}
      <div className="row">
        {onCancel && <button type="button" onClick={onCancel}>Cancelar</button>}
        <button className="primary" disabled={!name.trim() || !changed}>{role ? "Guardar rol" : "Crear rol"}</button>
      </div>
    </form>
  );
}
