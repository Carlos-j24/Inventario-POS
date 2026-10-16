import { useCallback, useEffect, useState, type FormEvent } from "react";

import { api, type AppUser, type Role } from "../api";
import { useMe } from "../auth";

/** Spec 003, T5: el administrador gestiona usuarios. Los usuarios no se borran: se desactivan. */
export default function Users() {
  const [users, setUsers] = useState<AppUser[] | null>(null);
  const [roles, setRoles] = useState<Role[]>([]);
  const [text, setText] = useState("");
  const [showInactive, setShowInactive] = useState(false);
  const [selected, setSelected] = useState<number | "new" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => api<AppUser[]>("/api/accounts/users/").then(setUsers).catch((e) => setError(e.message)), []);

  useEffect(() => {
    load();
    api<Role[]>("/api/accounts/roles/").then(setRoles).catch((e) => setError(e.message));
  }, [load]);

  const shown = (users ?? [])
    .filter((u) => showInactive || u.is_active)
    .filter((u) => `${u.username} ${u.first_name} ${u.last_name}`.toLowerCase().includes(text.trim().toLowerCase()));
  const current = typeof selected === "number" ? users?.find((u) => u.id === selected) : undefined;

  return (
    <div className="two-cols">
      <section className="card">
        <div className="row spread">
          <h2>Usuarios</h2>
          <button className="primary" onClick={() => setSelected("new")}>Nuevo usuario</button>
        </div>
        <div className="row filters">
          <input placeholder="Buscar…" value={text} onChange={(e) => setText(e.target.value)} aria-label="Buscar usuario" />
          <label className="check">
            <input type="checkbox" checked={showInactive} onChange={(e) => setShowInactive(e.target.checked)} /> Mostrar inactivos
          </label>
        </div>
        {error && <p className="error" role="alert">{error}</p>}
        <table className="cart sales-list">
          <thead><tr><th>Usuario</th><th>Nombre</th><th>Roles</th><th /></tr></thead>
          <tbody>
            {shown.map((u) => (
              <tr key={u.id} className={u.id === selected ? "selected" : !u.is_active ? "voided" : ""} onClick={() => setSelected(u.id)}>
                <td><button className="link" onClick={() => setSelected(u.id)}>{u.username}</button></td>
                <td>{`${u.first_name} ${u.last_name}`.trim() || "—"}</td>
                <td>{u.roles.join(", ") || <span className="muted">sin rol</span>}</td>
                <td>
                  <span className="row badges">
                    {!u.is_active && <span className="badge danger">Inactivo</span>}
                    {u.must_change_password && <span className="badge warn">Clave temporal</span>}
                  </span>
                </td>
              </tr>
            ))}
            {users && shown.length === 0 && <tr><td colSpan={4} className="muted center">Ningún usuario.</td></tr>}
          </tbody>
        </table>
      </section>
      <aside className="card">
        {selected === "new" && (
          <NewUser roles={roles} onCreated={(u) => { load(); setSelected(u.id); }} onCancel={() => setSelected(null)} />
        )}
        {current && <EditUser key={current.id} user={current} roles={roles} onSaved={load} />}
        {selected === null && <p className="muted">Elige un usuario o crea uno nuevo.</p>}
      </aside>
    </div>
  );
}

function RoleChecks({ roles, value, onChange }: { roles: Role[]; value: string[]; onChange: (v: string[]) => void }) {
  return (
    <fieldset className="role-checks">
      <legend>Roles</legend>
      {roles.map((r) => (
        <label key={r.id} className="check">
          <input
            type="checkbox"
            checked={value.includes(r.name)}
            onChange={(e) => onChange(e.target.checked ? [...value, r.name] : value.filter((n) => n !== r.name))}
          />
          {r.name}
        </label>
      ))}
    </fieldset>
  );
}

function NewUser({ roles, onCreated, onCancel }: { roles: Role[]; onCreated: (u: AppUser) => void; onCancel: () => void }) {
  const [form, setForm] = useState({ username: "", first_name: "", last_name: "", password: "" });
  const [chosen, setChosen] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value });

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      onCreated(await api<AppUser>("/api/accounts/users/", { method: "POST", body: { ...form, roles: chosen } }));
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <form className="action-form" onSubmit={submit}>
      <h2>Nuevo usuario</h2>
      <label>Usuario<input value={form.username} onChange={set("username")} autoFocus autoComplete="off" /></label>
      <div className="row">
        <label>Nombre<input value={form.first_name} onChange={set("first_name")} /></label>
        <label>Apellido<input value={form.last_name} onChange={set("last_name")} /></label>
      </div>
      <label>
        Contraseña temporal
        <input value={form.password} onChange={set("password")} autoComplete="new-password" />
      </label>
      <p className="muted small">Dísela al empleado: la app le pedirá cambiarla al entrar por primera vez.</p>
      <RoleChecks roles={roles} value={chosen} onChange={setChosen} />
      {error && <p className="error" role="alert">{error}</p>}
      <div className="row">
        <button type="button" onClick={onCancel}>Cancelar</button>
        <button className="primary" disabled={!form.username.trim() || !form.password}>Crear usuario</button>
      </div>
    </form>
  );
}

function EditUser({ user, roles, onSaved }: { user: AppUser; roles: Role[]; onSaved: () => void }) {
  const me = useMe();
  const isMe = me?.id === user.id;
  const [chosen, setChosen] = useState(user.roles);
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  /** Guarda un cambio y dice si salió bien (para no limpiar el formulario si el servidor lo rechazó). */
  async function patch(body: Record<string, unknown>, done: string): Promise<boolean> {
    setError(null);
    setMessage(null);
    try {
      await api(`/api/accounts/users/${user.id}/`, { method: "PATCH", body });
      setMessage(done);
      onSaved();
      return true;
    } catch (err) {
      setError((err as Error).message);
      return false;
    }
  }

  const rolesChanged = [...chosen].sort().join() !== [...user.roles].sort().join();

  return (
    <div className="action-form">
      <h2>{user.username}</h2>
      <p className="muted">
        {`${user.first_name} ${user.last_name}`.trim() || "Sin nombre"} ·{" "}
        {user.last_login ? `último ingreso ${new Date(user.last_login).toLocaleString("es-CO")}` : "nunca ha entrado"}
      </p>

      <RoleChecks roles={roles} value={chosen} onChange={setChosen} />
      <button disabled={!rolesChanged} onClick={() => patch({ roles: chosen }, "Roles guardados.")}>Guardar roles</button>

      <h3>Contraseña nueva</h3>
      <div className="row">
        <input
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder={isMe ? "Tu nueva contraseña" : "Contraseña temporal"}
          aria-label="Contraseña nueva"
          autoComplete="new-password"
        />
        <button
          disabled={!password}
          onClick={() => patch({ password }, isMe ? "Contraseña cambiada." : "Contraseña temporal puesta: deberá cambiarla al entrar.").then((ok) => ok && setPassword(""))}
        >
          Poner contraseña
        </button>
      </div>

      <h3>Acceso</h3>
      {user.is_active ? (
        <button
          className="danger-btn"
          disabled={isMe}
          title={isMe ? "No puedes desactivar tu propio usuario." : undefined}
          onClick={() => patch({ is_active: false }, "Usuario desactivado: ya no puede entrar.")}
        >
          Desactivar usuario
        </button>
      ) : (
        <button onClick={() => patch({ is_active: true }, "Usuario reactivado.")}>Reactivar usuario</button>
      )}
      {isMe && <p className="muted small">Este es tu usuario: no puedes desactivarte a ti mismo.</p>}

      {message && <p className="change" role="status">{message}</p>}
      {error && <p className="error" role="alert">{error}</p>}
    </div>
  );
}
