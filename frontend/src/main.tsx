import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import { AuthProvider } from "./auth";
import "./install"; // escucha "beforeinstallprompt" desde el arranque
import { SyncProvider } from "./sync";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AuthProvider>
      <SyncProvider>
        <App />
      </SyncProvider>
    </AuthProvider>
  </StrictMode>,
);

// El service worker guarda la app para abrirla sin red. Solo en producción: en desarrollo
// interferiría con la recarga en caliente de Vite.
if (import.meta.env.PROD && "serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch((err) => console.error("Service worker:", err));
  });
}
