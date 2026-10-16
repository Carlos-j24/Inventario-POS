import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

import { api, ApiError, type Me } from "./api";
import { kv } from "./idb";
import { isUnreachable } from "./offline";

interface AuthState {
  user: Me | null;
  loading: boolean;
  /** true si el usuario viene de la copia local porque no hubo red al abrir la app. */
  offlineSession: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  can: (permission: string) => boolean;
}

const AuthContext = createContext<AuthState | null>(null);
const ME_KEY = "me";

// La copia local permite abrir la caja sin red. El servidor vuelve a validar la sesión
// al sincronizar; si venció, el cajero inicia sesión otra vez y la cola se envía.
const saveMe = (me: Me | null) => (me ? kv.set(ME_KEY, me) : kv.remove(ME_KEY)).catch(() => {});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const [offlineSession, setOfflineSession] = useState(false);

  useEffect(() => {
    // Primero la cookie CSRF; luego, si ya hay sesión abierta, quién es el usuario.
    api("/api/auth/csrf/")
      .then(() => api<Me>("/api/auth/me/"))
      .then((me) => { setUser(me); saveMe(me); })
      .catch(async (err) => {
        if (isUnreachable(err)) {
          const cached = await kv.get<Me>(ME_KEY).catch(() => undefined);
          if (cached) { setUser(cached); setOfflineSession(true); }
        } else if (err instanceof ApiError) {
          saveMe(null); // sin sesión en el servidor: se olvida la copia local
        } else {
          console.error(err);
        }
      })
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const me = await api<Me>("/api/auth/login/", { method: "POST", body: { username, password } });
    setUser(me);
    setOfflineSession(false);
    saveMe(me);
  }, []);

  const logout = useCallback(async () => {
    try {
      await api("/api/auth/logout/", { method: "POST" });
    } catch (err) {
      if (!isUnreachable(err)) throw err; // sin red se cierra igual en este equipo
    }
    setUser(null);
    saveMe(null);
  }, []);

  const can = useCallback((permission: string) => !!user?.permissions.includes(permission), [user]);

  return (
    <AuthContext.Provider value={{ user, loading, offlineSession, login, logout, can }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth fuera de AuthProvider");
  return ctx;
}

/** can() para mostrar u ocultar acciones. Sin sesión cargada (o fuera del proveedor), nada está permitido. */
export function useCan(): (permission: string) => boolean {
  return useContext(AuthContext)?.can ?? (() => false);
}

/** El usuario con sesión, o null (también fuera del proveedor, p. ej. en tests de una pantalla). */
export function useMe(): Me | null {
  return useContext(AuthContext)?.user ?? null;
}
