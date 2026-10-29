// Service worker de Inventario POS: guarda la app (HTML, JS, CSS) para abrirla sin red.
// Los datos (/api) no pasan por aquí: la app los guarda en IndexedDB y decide qué hacer sin red.
const CACHE = "pos-app-v1";

/** Rutas que enlaza la página (los de /assets llevan hash en el nombre). */
function linkedPaths(html) {
  return [...html.matchAll(/(?:src|href)="(\/[^"]+)"/g)].map((m) => m[1]).filter((p) => !p.startsWith("/api/"));
}

/**
 * Guarda la página como copia sin red y borra los /assets de versiones anteriores que ya no
 * enlaza: sin esto la caché crecería con cada actualización. Solo con respuestas correctas,
 * para no reemplazar la copia buena por una página de error.
 */
async function rememberPage(res) {
  if (!res.ok) return;
  const cache = await caches.open(CACHE);
  const html = await res.clone().text();
  await cache.put("/", res.clone());
  const keep = new Set(linkedPaths(html));
  for (const req of await cache.keys()) {
    const path = new URL(req.url).pathname;
    if (path.startsWith("/assets/") && !keep.has(path)) await cache.delete(req);
  }
  return keep;
}

self.addEventListener("install", (event) => {
  event.waitUntil(
    (async () => {
      const res = await fetch("/", { cache: "no-store" });
      const keep = await rememberPage(res);
      if (keep) await (await caches.open(CACHE)).addAll([...keep]);
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
  if (url.pathname === "/sw.js") return; // el propio service worker siempre de la red

  if (req.mode === "navigate") {
    // Red primero para recibir versiones nuevas; sin red (o con error del servidor), la copia guardada.
    event.respondWith(
      (async () => {
        try {
          const res = await fetch(req);
          if (res.ok) {
            event.waitUntil(rememberPage(res.clone()));
            return res;
          }
          return (await caches.match("/")) ?? res;
        } catch {
          return (await caches.match("/")) ?? Response.error();
        }
      })(),
    );
    return;
  }

  // Logo, íconos y manifiesto del negocio (/brand): red primero, para que un logo nuevo llegue;
  // sin red, la copia guardada. Si la instalación no trae logo (404), no se guarda nada.
  if (url.pathname.startsWith("/brand/")) {
    event.respondWith(
      (async () => {
        try {
          const res = await fetch(req);
          if (res.ok) (await caches.open(CACHE)).put(req, res.clone());
          return res;
        } catch {
          return (await caches.match(req)) ?? Response.error();
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
