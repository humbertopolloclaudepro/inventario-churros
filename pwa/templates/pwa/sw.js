{% load static %}// Service worker: guarda la "cáscara" de la app para que abra rápido y sin red.
// La API nunca se guarda en caché: el stock siempre se pide al servidor.
// TODO (iteración, P1): cola offline de movimientos en IndexedDB que se envía al
// recuperar la conexión. La API ya acepta uuid_cliente para no duplicar.
const CACHE = "inventario-v1";
const ARCHIVOS = [
  "/app/",
  "{% static 'pwa/app.js' %}",
  "{% static 'pwa/styles.css' %}",
  "{% static 'pwa/icons/icon-192.png' %}",
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(ARCHIVOS)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((claves) => Promise.all(claves.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/admin/")) return;

  if (e.request.mode === "navigate") {
    // Red primero; si no hay red, la última versión guardada.
    e.respondWith(
      fetch(e.request)
        .then((r) => {
          if (r.ok && url.pathname === "/app/") {
            const copia = r.clone();
            caches.open(CACHE).then((c) => c.put("/app/", copia));
          }
          return r;
        })
        .catch(() => caches.match("/app/"))
    );
    return;
  }
  // Archivos estáticos: caché primero.
  e.respondWith(caches.match(e.request).then((r) => r || fetch(e.request)));
});
