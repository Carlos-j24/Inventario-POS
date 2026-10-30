import { useState, type ComponentType } from "react";

import { useAuth } from "./auth";
import BrandLogo from "./components/BrandLogo";
import { promptInstall, useCanInstall } from "./install";
import Adjustments from "./pages/Adjustments";
import ChangePassword from "./pages/ChangePassword";
import Counts from "./pages/Counts";
import Transfers from "./pages/Transfers";
import FiscalInbox from "./pages/FiscalInbox";
import Login from "./pages/Login";
import Maintenance from "./pages/Maintenance";
import Motorcycles from "./pages/Motorcycles";
import MyOrders from "./pages/MyOrders";
import Orders from "./pages/Orders";
import Quotes from "./pages/Quotes";
import Pos from "./pages/Pos";
import Products from "./pages/Products";
import Receipts from "./pages/Receipts";
import Review from "./pages/Review";
import Reports from "./pages/Reports";
import Roles from "./pages/Roles";
import Sales from "./pages/Sales";
import Stock from "./pages/Stock";
import Users from "./pages/Users";
import WorkOrders from "./pages/WorkOrders";
import { useSync } from "./sync";

// Cada pantalla aparece si el usuario tiene alguno de sus permisos; el backend vuelve a comprobarlo.
// Las del taller, además, solo si la instalación tiene el módulo activo (spec 009).
const PAGES: { id: string; label: string; permission: string | string[]; workshop?: true; Component: ComponentType }[] = [
  { id: "pos", label: "Caja", permission: "cash.operate", Component: Pos },
  { id: "work-orders", label: "Órdenes", permission: "workshop.receive", workshop: true, Component: WorkOrders },
  { id: "my-orders", label: "Mis órdenes", permission: "workshop.repair", workshop: true, Component: MyOrders },
  { id: "motorcycles", label: "Motos", permission: "workshop.receive", workshop: true, Component: Motorcycles },
  { id: "orders", label: "Pedidos", permission: "sales.create", Component: Orders },
  { id: "quotes", label: "Cotizaciones", permission: ["sales.create", "sales.void", "reports.view"], Component: Quotes },
  { id: "receipts", label: "Entradas", permission: "inventory.receive", Component: Receipts },
  { id: "stock", label: "Existencias", permission: "inventory.view", Component: Stock },
  { id: "products", label: "Productos", permission: "catalog.edit", Component: Products },
  // Después de Productos: quien maneja el catálogo sigue abriendo en sus pantallas de siempre.
  { id: "maintenance", label: "Mantenimientos", permission: ["workshop.receive", "catalog.edit"], workshop: true, Component: Maintenance },
  { id: "counts", label: "Conteos", permission: ["inventory.count", "inventory.adjust"], Component: Counts },
  { id: "adjustments", label: "Ajustes", permission: ["inventory.receive", "inventory.count", "inventory.adjust"], Component: Adjustments },
  { id: "transfers", label: "Traslados", permission: "inventory.transfer", Component: Transfers },
  { id: "sales", label: "Ventas", permission: ["sales.void", "reports.view"], Component: Sales },
  { id: "review", label: "Revisión", permission: "reports.view", Component: Review },
  { id: "reports", label: "Reportes", permission: "reports.view", Component: Reports },
  { id: "fiscal", label: "DIAN", permission: "reports.view", Component: FiscalInbox },
  { id: "users", label: "Usuarios", permission: "users.manage", Component: Users },
  { id: "roles", label: "Roles", permission: "users.manage", Component: Roles },
];

export default function App() {
  const { user, loading, logout, can } = useAuth();
  const [current, setCurrent] = useState<string | null>(null);

  if (loading) return <p className="center muted">Cargando…</p>;
  if (!user) return <Login />;
  // Contraseña temporal: hasta cambiarla no hay nada más (la API tampoco lo permite).
  if (user.must_change_password) return <ChangePassword forced />;

  const pages = PAGES.filter((p) => (!p.workshop || user.workshop_enabled) && [p.permission].flat().some(can));
  const page = current === "password" ? null : pages.find((p) => p.id === current) ?? pages[0];

  return (
    <div className="app">
      <header className="topbar">
        <BrandLogo className="topbar-logo" />
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
        <InstallButton />
        <button className="link user" onClick={() => setCurrent("password")} title="Cambiar mi contraseña">
          {user.first_name || user.username} · {user.roles.join(", ") || "sin rol"}
        </button>
        <LogoutButton onLogout={logout} />
      </header>
      <SyncMessage />
      <main className="content">
        {current === "password" ? (
          <ChangePassword />
        ) : page ? (
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

function InstallButton() {
  const canInstall = useCanInstall();
  if (!canInstall) return null;
  return (
    <button className="link" onClick={() => promptInstall()} title="Instalar en este equipo para abrirla como una aplicación">
      Instalar app
    </button>
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
