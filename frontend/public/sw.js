// Service worker de Inventario POS: guarda la app (HTML, JS, CSS) para abrirla sin red.
// Los datos (/api) no pasan por aquí: la app los guarda en IndexedDB y decide qué hacer sin red.
const CACHE = "pos-app-v1";

// Al instalar se guardan la página y los archivos que enlaza (los de /assets llevan hash en el nombre).
self.addEventListener("install", (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(CACHE);
      const res = await fetch("/", { cache: "no-store" });
      const html = await res.clone().text();
      await cache.put("/", res);
      const assets = [...html.matchAll(/(?:src|href)="(\/[^"]+)"/g)].map((m) => m[1]);
      await cache.addAll(assets.filter((a) => !a.startsWith("/api/")));
      await self.skipWaiting();
    })(),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      for (const key of await caches.keys()) if (key !== CACHE) await caches.delete(key);
      await self.clients.claim();
    })(),
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  const url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/admin") || url.pathname.startsWith("/static")) return;

  if (req.mode === "navigate") {
    // Red primero para recibir versiones nuevas; sin red, la copia guardada.
    event.respondWith(
      (async () => {
        try {
          const res = await fetch(req);
          (await caches.open(CACHE)).put("/", res.clone());
          return res;
        } catch {
          return (await caches.match("/")) ?? Response.error();
        }
      })(),
    );
    return;
  }

  // Archivos estáticos: la copia guardada si existe; si no, la red (y se guarda).
  event.respondWith(
    (async () => {
      const cached = await caches.match(req);
      if (cached) return cached;
      const res = await fetch(req);
      if (res.ok) (await caches.open(CACHE)).put(req, res.clone());
      return res;
    })(),
  );
});
