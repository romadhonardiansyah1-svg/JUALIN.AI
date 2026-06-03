/**
 * JUALIN.AI — API Helper
 * Centralized fetch wrapper with auth header injection + simple caching
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

// ── Debounce utility (BUG 15 FIX) ──
export function debounce(fn, delay = 300) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}

// ── Simple in-memory cache ──
const _cache = {};
const CACHE_TTL = 60000; // 1 minute

function getCached(key) {
  const entry = _cache[key];
  if (!entry) return null;
  if (Date.now() - entry.timestamp > CACHE_TTL) {
    delete _cache[key];
    return null;
  }
  return entry.data;
}

function setCache(key, data, ttl = CACHE_TTL) {
  _cache[key] = { data, timestamp: Date.now(), ttl };
}

function clearCache(prefix) {
  Object.keys(_cache).forEach((k) => {
    if (!prefix || k.startsWith(prefix)) delete _cache[k];
  });
}

// ── Fetch wrapper ──
async function fetchAPI(endpoint, options = {}) {
  const token =
    typeof window !== "undefined" ? localStorage.getItem("jualin_token") : null;

  const headers = {
    "Content-Type": "application/json",
    ...(token && { Authorization: `Bearer ${token}` }),
    ...options.headers,
  };

  const res = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers,
  });

  if (res.status === 401) {
    if (typeof window !== "undefined") {
      localStorage.removeItem("jualin_token");
      localStorage.removeItem("jualin_user");
      window.location.href = "/login";
    }
    throw new Error("Session expired");
  }

  const data = await res.json();

  if (!res.ok) {
    throw new Error(data.detail || "Something went wrong");
  }

  return data;
}

// ── Cached fetch (for data that rarely changes) ──
async function fetchCached(endpoint, options = {}, ttl = CACHE_TTL) {
  const cacheKey = `api:${endpoint}`;
  const cached = getCached(cacheKey);
  if (cached) return cached;

  const data = await fetchAPI(endpoint, options);
  setCache(cacheKey, data, ttl);
  return data;
}

// ── File upload helper ──
async function uploadFile(endpoint, file, extraData = {}) {
  const token =
    typeof window !== "undefined" ? localStorage.getItem("jualin_token") : null;

  const formData = new FormData();
  formData.append("file", file);
  Object.entries(extraData).forEach(([key, val]) =>
    formData.append(key, val)
  );

  const res = await fetch(`${API_BASE}${endpoint}`, {
    method: "POST",
    headers: {
      ...(token && { Authorization: `Bearer ${token}` }),
      // Don't set Content-Type — browser sets it with boundary for FormData
    },
    body: formData,
  });

  if (res.status === 401) {
    if (typeof window !== "undefined") {
      localStorage.removeItem("jualin_token");
      localStorage.removeItem("jualin_user");
      window.location.href = "/login";
    }
    throw new Error("Session expired");
  }

  const data = await res.json();

  if (!res.ok) {
    throw new Error(data.detail || "Upload gagal");
  }

  return data;
}

// Auth
export const api = {
  // Auth
  register: (body) =>
    fetchAPI("/api/auth/register", { method: "POST", body: JSON.stringify(body) }),
  login: (body) =>
    fetchAPI("/api/auth/login", { method: "POST", body: JSON.stringify(body) }),
  getMe: () => fetchAPI("/api/auth/me"),
  updateSettings: (body) =>
    fetchAPI("/api/auth/settings", { method: "PATCH", body: JSON.stringify(body) }),

  // Products
  getProducts: () => fetchAPI("/api/products/"),
  createProduct: (body) => {
    clearCache("api:/api/products");
    return fetchAPI("/api/products/", { method: "POST", body: JSON.stringify(body) });
  },
  updateProduct: (id, body) => {
    clearCache("api:/api/products");
    return fetchAPI(`/api/products/${id}`, { method: "PUT", body: JSON.stringify(body) });
  },
  deleteProduct: (id) => {
    clearCache("api:/api/products");
    return fetchAPI(`/api/products/${id}`, { method: "DELETE" });
  },
  uploadProductImage: (productId, file) => {
    clearCache("api:/api/products");
    return uploadFile(`/api/products/${productId}/upload-image`, file);
  },
  searchProducts: (q, sellerId) =>
    fetchAPI(`/api/products/search?q=${encodeURIComponent(q)}&seller_id=${sellerId}`),

  // Chat
  sendChat: (body) =>
    fetchAPI("/api/chat/send", { method: "POST", body: JSON.stringify(body) }),
  getChatHistory: (sessionId) => fetchAPI(`/api/chat/history/${sessionId}`),
  getConversations: () => fetchAPI("/api/chat/conversations"),
  getQuota: () => fetchCached("/api/chat/quota", {}, 30000), // Cache 30s

  // Orders
  getOrders: (status) =>
    fetchAPI(`/api/orders/${status ? `?status=${status}` : ""}`),
  getOrder: (id) => fetchAPI(`/api/orders/${id}`),
  updateOrderStatus: (id, body) => {
    clearCache("api:/api/orders");
    clearCache("api:/api/analytics");
    return fetchAPI(`/api/orders/${id}/status`, { method: "PATCH", body: JSON.stringify(body) });
  },

  // Analytics
  getSummary: () => fetchCached("/api/analytics/summary", {}, 30000), // Cache 30s
  getOrdersDaily: (days = 7) =>
    fetchCached(`/api/analytics/orders-daily?days=${days}`, {}, 60000),
  getTopProducts: () =>
    fetchCached("/api/analytics/top-products", {}, 60000),

  // Admin
  getAdminStats: () => fetchAPI("/api/admin/stats"),
  getAdminSellers: () => fetchAPI("/api/admin/sellers"),
  updateAdminSeller: (id, body) =>
    fetchAPI(`/api/admin/sellers/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  getSystemHealth: () => fetchAPI("/api/admin/system"),

  // Utility
  clearCache: () => clearCache(),
};
