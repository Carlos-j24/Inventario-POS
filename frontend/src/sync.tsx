import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";

import { api } from "./api";
import { useAuth } from "./auth";
import { outboxDb } from "./idb";
import { syncOutbox, type OutboxStore, type QueuedSale } from "./offline";

const RETRY_MS = 30_000;
const store = outboxDb as OutboxStore;

interface SyncState {
  online: boolean;
  pending: QueuedSale[];
  failed: QueuedSale[];
  syncing: boolean;
  message: string | null;
  enqueue: (item: QueuedSale) => Promise<void>;
  syncNow: () => Promise<void>;
}

const SyncContext = createContext<SyncState | null>(null);

export function SyncProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const [online, setOnline] = useState(navigator.onLine);
  const [items, setItems] = useState<QueuedSale[]>([]);
  const [syncing, setSyncing] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const running = useRef(false);

  const refresh = useCallback(async () => {
    try {
      setItems(await store.all());
    } catch {
      setItems([]); // navegador sin IndexedDB (modo privado estricto): no hay cola
    }
  }, []);

  const syncNow = useCallback(async () => {
    if (!user || running.current) return;
    running.current = true;
    setSyncing(true);
    try {
      const r = await syncOutbox(store, user.username, (body) => api("/api/sales/", { method: "POST", body }));
      setOnline(r.stopped !== "offline");
      setMessage(
        r.stopped === "auth"
          ? "La sesión venció: sal y vuelve a entrar para enviar las ventas pendientes."
          : r.failed
            ? `${r.failed} venta(s) rechazada(s) por el servidor: avisa al supervisor.`
            : r.sent
              ? `${r.sent} venta(s) sin conexión enviada(s).`
              : null,
      );
    } finally {
      running.current = false;
      setSyncing(false);
      await refresh();
    }
  }, [user, refresh]);

  const enqueue = useCallback(
    async (item: QueuedSale) => {
      await store.put(item);
      setOnline(false);
      await refresh();
    },
    [refresh],
  );

  useEffect(() => {
    refresh();
    const goOnline = () => { setOnline(true); syncNow(); };
    const goOffline = () => setOnline(false);
    window.addEventListener("online", goOnline);
    window.addEventListener("offline", goOffline);
    const timer = window.setInterval(syncNow, RETRY_MS);
    syncNow();
    return () => {
      window.removeEventListener("online", goOnline);
      window.removeEventListener("offline", goOffline);
      window.clearInterval(timer);
    };
  }, [refresh, syncNow]);

  const mine = items.filter((i) => i.username === user?.username);
  return (
    <SyncContext.Provider
      value={{
        online,
        pending: mine.filter((i) => i.status === "pending"),
        failed: mine.filter((i) => i.status === "failed"),
        syncing,
        message,
        enqueue,
        syncNow,
      }}
    >
      {children}
    </SyncContext.Provider>
  );
}

export function useSync(): SyncState {
  const ctx = useContext(SyncContext);
  if (!ctx) throw new Error("useSync fuera de SyncProvider");
  return ctx;
}
