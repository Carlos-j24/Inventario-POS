import { useState, type FormEvent } from "react";

import { useAuth } from "../auth";

/**
 * Cambiar la contraseña propia. Con forced, es la pantalla obligatoria del primer ingreso:
 * la contraseña la puso un administrador y la API no deja hacer nada más hasta cambiarla.
 */
export default function ChangePassword({ forced = false, onDone }: { forced?: boolean; onDone?: () => void }) {
  const { user, changePassword, logout } = useAuth();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [repeat, setRepeat] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  const mismatch = repeat.length > 0 && next !== repeat;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await changePassword(current, next);
      setDone(true);
      setCurrent(""); setNext(""); setRepeat("");
      onDone?.();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className={forced ? "card login" : "card narrow"} onSubmit={submit}>
      <h2>{forced ? `Hola, ${user?.first_name || user?.username}` : "Cambiar mi contraseña"}</h2>
      {forced && (
        <p className="muted">
          Entraste con una contraseña temporal que te dio el administrador. Crea la tuya para empezar; solo tú la vas a
          conocer.
        </p>
      )}
      <label>
        {forced ? "Contraseña temporal" : "Contraseña actual"}
        <input type="password" value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" autoFocus />
      </label>
      <label>
        Nueva contraseña
        <input type="password" value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" />
      </label>
      <label>
        Repite la nueva
        <input type="password" value={repeat} onChange={(e) => setRepeat(e.target.value)} autoComplete="new-password" />
      </label>
      <p className="muted small">Al menos 8 caracteres, que no sea solo números ni se parezca a tu usuario.</p>
      {mismatch && <p className="error">Las contraseñas nuevas no coinciden.</p>}
      {error && <p className="error" role="alert">{error}</p>}
      {done && !forced && <p className="change" role="status">Contraseña cambiada.</p>}
      <button className="primary" disabled={busy || !current || !next || next !== repeat}>
        {busy ? "Guardando…" : "Cambiar contraseña"}
      </button>
      {forced && <button type="button" className="link" onClick={logout}>Salir</button>}
    </form>
  );
}
