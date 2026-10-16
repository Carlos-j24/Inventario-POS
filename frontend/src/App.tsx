import { useState } from "react";

import { useAuth } from "./auth";
import Login from "./pages/Login";
import Pos from "./pages/Pos";
import Receipts from "./pages/Receipts";
import Review from "./pages/Review";
import Stock from "./pages/Stock";
import { useSync } from "./sync";

// Cada pantalla aparece solo si el usuario tiene el permiso; el backend vuelve a comprobarlo.
const PAGES = [
  { id: "pos", label: "Caja", permission: "cash.operate", Component: Pos },
  { id: "receipts", label: "Entradas", permission: "inventory.receive", Component: Receipts },
  { id: "stock", label: "Existencias", permission: "inventory.view", Component: Stock },
  { id: "review", label: "Revisión", permission: "reports.view", Component: Review },
] as const;

export default function App() {
  const { user, loading, logout, can } = useAuth();
  const [current, setCurrent] = useState<string | null>(null);

  if (loading) return <p className="center muted">Cargando…</p>;
  if (!user) return <Login />;

  const pages = PAGES.filter((p) => can(p.permission));
  const page = pages.find((p) => p.id === current) ?? pages[0];

  return (
    <div className="app">
      <header className="topbar">
        <strong className="brand">Inventario POS</strong>
        <nav>
          {pages.map((p) => (
            <button
              key={p.id}
              className={p.id === page?.id ? "tab active" : "tab"}
              onClick={() => setCurrent(p.id)}
            >
              {p.label}
            </button>
          ))}
        </nav>
        <SyncStatus />
        <span className="user">
          {user.first_name || user.username} · {user.roles.join(", ") || "sin rol"}
        </span>
        <LogoutButton onLogout={logout} />
      </header>
      <SyncMessage />
      <main className="content">
        {page ? (
          <page.Component />
        ) : (
          <p className="center muted">Tu usuario no tiene pantallas asignadas. Pide un rol al administrador.</p>
        )}
      </main>
    </div>
  );
}

function SyncStatus() {
  const { online, pending, failed, syncing, syncNow } = useSync();
  return (
    <span className="sync">
      <span className={online ? "dot ok" : "dot off"} aria-hidden />
      {online ? "En línea" : "Sin conexión"}
      {pending.length > 0 && <span className="badge warn">{pending.length} por enviar</span>}
      {failed.length > 0 && <span className="badge danger">{failed.length} rechazada(s)</span>}
      {pending.length > 0 && (
        <button className="link" onClick={syncNow} disabled={syncing}>
          {syncing ? "Enviando…" : "Enviar ahora"}
        </button>
      )}
    </span>
  );
}

function SyncMessage() {
  const { message, failed, online } = useSync();
  const { offlineSession } = useAuth();
  const offlineNote = offlineSession && !online;
  if (!message && !failed.length && !offlineNote) return null;
  return (
    <div className="banner" role="status">
      {offlineNote && <p>Abriste la app sin conexión con la sesión guardada en este equipo.</p>}
      {message && <p>{message}</p>}
      {failed.map((f) => (
        <p key={f.client_uuid} className="error">
          Venta del {new Date(f.createdAt).toLocaleString("es-CO")} rechazada: {f.error}
        </p>
      ))}
    </div>
  );
}

function LogoutButton({ onLogout }: { onLogout: () => Promise<void> }) {
  const { pending } = useSync();
  function click() {
    if (
      pending.length &&
      !window.confirm(
        `Hay ${pending.length} venta(s) sin enviar. Se enviarán cuando vuelvas a entrar con este usuario. ¿Salir?`,
      )
    ) {
      return;
    }
    onLogout();
  }
  return (
    <button className="link" onClick={click}>
      Salir
    </button>
  );
}
