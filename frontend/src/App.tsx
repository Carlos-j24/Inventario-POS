import { useState } from "react";

import { useAuth } from "./auth";
import Login from "./pages/Login";
import Pos from "./pages/Pos";
import Receipts from "./pages/Receipts";
import Stock from "./pages/Stock";

// Cada pantalla aparece solo si el usuario tiene el permiso; el backend vuelve a comprobarlo.
const PAGES = [
  { id: "pos", label: "Caja", permission: "cash.operate", Component: Pos },
  { id: "receipts", label: "Entradas", permission: "inventory.receive", Component: Receipts },
  { id: "stock", label: "Existencias", permission: "inventory.view", Component: Stock },
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
        <span className="user">
          {user.first_name || user.username} · {user.roles.join(", ") || "sin rol"}
        </span>
        <button className="link" onClick={logout}>
          Salir
        </button>
      </header>
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
