/**
 * JUALIN.AI — API Helper
 * Centralized fetch wrapper with auth header injection
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

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

// Auth
export const api = {
  // Auth
  register: (body) =>
    fetchAPI("/api/auth/register", { method: "POST", body: JSON.stringify(body) }),
  login: (body) =>
    fetchAPI("/api/auth/login", { method: "POST", body: JSON.stringify(body) }),
  getMe: () => fetchAPI("/api/auth/me"),

  // Products
  getProducts: () => fetchAPI("/api/products/"),
  createProduct: (body) =>
    fetchAPI("/api/products/", { method: "POST", body: JSON.stringify(body) }),
  updateProduct: (id, body) =>
    fetchAPI(`/api/products/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  deleteProduct: (id) =>
    fetchAPI(`/api/products/${id}`, { method: "DELETE" }),
  searchProducts: (q, sellerId) =>
    fetchAPI(`/api/products/search?q=${encodeURIComponent(q)}&seller_id=${sellerId}`),

  // Chat
  sendChat: (body) =>
    fetchAPI("/api/chat/send", { method: "POST", body: JSON.stringify(body) }),
  getChatHistory: (sessionId) => fetchAPI(`/api/chat/history/${sessionId}`),
  getConversations: () => fetchAPI("/api/chat/conversations"),
  getQuota: () => fetchAPI("/api/chat/quota"),

  // Orders
  getOrders: (status) =>
    fetchAPI(`/api/orders/${status ? `?status=${status}` : ""}`),
  getOrder: (id) => fetchAPI(`/api/orders/${id}`),
  updateOrderStatus: (id, body) =>
    fetchAPI(`/api/orders/${id}/status`, { method: "PATCH", body: JSON.stringify(body) }),

  // Analytics
  getSummary: () => fetchAPI("/api/analytics/summary"),
  getOrdersDaily: (days = 7) =>
    fetchAPI(`/api/analytics/orders-daily?days=${days}`),
  getTopProducts: () => fetchAPI("/api/analytics/top-products"),
};
