/**
 * JUALIN.AI — Minimal Service Worker (P0.3b containment)
 * P0.3b: MUST NOT cache authenticated navigation, dashboard HTML/RSC, or /api/*
 * Only caches versioned static assets (.js/.css/.png/.ico) with network-first.
 */

const CACHE_NAME = "jualin-shell-v2";

// Only public static entry points — NEVER dashboard or authenticated HTML/RSC
const SHELL_URLS = [
  // Intentionally minimal: only public pages that are safe to cache offline.
  // Dashboard, login, register are NOT cached because they may contain tenant data.
];

self.addEventListener("install", (event) => {
  // Pre-cache nothing sensitive; optionally cache nothing at install to avoid stale dashboard
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      if (SHELL_URLS.length === 0) return;
      return cache.addAll(SHELL_URLS).catch(() => {});
    })
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => k !== CACHE_NAME)
          .map((k) => {
            // Purge all legacy jualin caches, especially v1 that contained /dashboard, /login, /register
            if (k.toLowerCase().includes("jualin") || k !== CACHE_NAME) {
              return caches.delete(k);
            }
            return Promise.resolve();
          })
      )
    )
  );
  self.clients.claim();
});

self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "PURGE_AUTH_CACHE") {
    event.waitUntil(
      caches.keys().then((keys) =>
        Promise.all(
          keys.map((k) => {
            if (k.toLowerCase().includes("jualin")) {
              return caches.delete(k);
            }
            return Promise.resolve();
          })
        )
      )
    );
  }
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // NEVER cache API calls, auth endpoints, dashboard HTML/RSC, or sensitive data
  if (
    url.pathname.startsWith("/api/") ||
    url.pathname.includes("/dashboard") ||
    url.pathname.includes("/login") ||
    url.pathname.includes("/register") ||
    url.pathname.includes("token") ||
    url.pathname.includes("_rsc") ||
    event.request.method !== "GET"
  ) {
    return;
  }

  // Network-first for static assets only
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        // Only cache successful responses for hashed static assets
        const isStaticAsset =
          url.pathname.endsWith(".js") ||
          url.pathname.endsWith(".css") ||
          url.pathname.endsWith(".png") ||
          url.pathname.endsWith(".ico") ||
          url.pathname.endsWith(".woff2") ||
          url.pathname.endsWith(".webp");
        if (response.ok && isStaticAsset) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
        }
        return response;
      })
      .catch(() => {
        // Fallback to cache only for static assets, never for HTML/RSC
        if (
          url.pathname.endsWith(".js") ||
          url.pathname.endsWith(".css") ||
          url.pathname.endsWith(".png") ||
          url.pathname.endsWith(".ico")
        ) {
          return caches.match(event.request);
        }
        return fetch(event.request);
      })
  );
});
