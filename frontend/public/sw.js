/**
 * JUALIN.AI — Minimal Service Worker
 * PWA installable, caches shell only. Does NOT cache sensitive data (tokens, API responses).
 */

const CACHE_NAME = "jualin-shell-v1";

// Only cache the app shell and static assets — never data
const SHELL_URLS = [
  "/dashboard",
  "/login",
  "/register",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(SHELL_URLS).catch(() => {
        // Skip if any URL fails
      });
    })
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // NEVER cache API calls, auth tokens, or sensitive data
  if (url.pathname.startsWith("/api/") || url.pathname.includes("token") || event.request.method !== "GET") {
    return;
  }

  // Network-first for everything else
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        // Only cache successful responses for static assets
        if (response.ok && (url.pathname.endsWith(".js") || url.pathname.endsWith(".css") || url.pathname.endsWith(".png") || url.pathname.endsWith(".ico"))) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
        }
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});
