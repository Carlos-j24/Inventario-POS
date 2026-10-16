// Botón "Instalar app": Chrome y Edge avisan con "beforeinstallprompt" que la app se puede instalar.
// El aviso llega una sola vez y muy pronto, así que se escucha al cargar este módulo (desde main.tsx).
import { useSyncExternalStore } from "react";

interface BeforeInstallPromptEvent extends Event {
  prompt(): Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

let deferred: BeforeInstallPromptEvent | null = null;
const listeners = new Set<() => void>();
const notify = () => listeners.forEach((l) => l());

window.addEventListener("beforeinstallprompt", (e) => {
  e.preventDefault(); // la app muestra su propio botón
  deferred = e as BeforeInstallPromptEvent;
  notify();
});
window.addEventListener("appinstalled", () => {
  deferred = null;
  notify();
});

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** true si el navegador ofrece instalar la app y todavía no está instalada. */
export function useCanInstall(): boolean {
  return useSyncExternalStore(subscribe, () => deferred !== null);
}

/** Abre el cuadro de instalación del navegador. Devuelve si el usuario aceptó. */
export async function promptInstall(): Promise<boolean> {
  if (!deferred) return false;
  const event = deferred;
  deferred = null; // el aviso solo se puede usar una vez
  notify();
  await event.prompt();
  const { outcome } = await event.userChoice;
  console.info(`[instalar] respuesta del navegador: ${outcome}`);
  return outcome === "accepted";
}
