/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// En desarrollo, Vite reenvía /api, /admin y /brand (logo del negocio) a Django para que el navegador vea un solo
// dominio: la sesión en cookie y el CSRF funcionan igual que en producción.
const backend = process.env.BACKEND_URL ?? "http://localhost:8000";
const proxy = { "/api": backend, "/admin": backend, "/static": backend, "/brand": backend };

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy,
  },
  // "vite preview" sirve la versión compilada (con service worker) para probar sin conexión.
  preview: {
    port: 4173,
    proxy,
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test-setup.ts"],
  },
});
