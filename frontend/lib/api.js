/**
 * JUALIN.AI — API Helper
 * Centralized fetch wrapper with auth header injection + tenant-isolated caching (P0.3b containment)
 *
 * Security fix BUG-025: cross-tenant cache isolation + service-worker purge
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

// ── Tenant-isolated in-memory cache with session epoch ──
// Immediate containment: seller-sensitive cache disabled until proper principal/session epoch
const _cache = {};
const CACHE_TTL = 60000; // 1 minute default, but sensitive endpoints bypass cache
let _sessionEpoch = 0;
const ENABLE_AUTH_CACHE = false; // P0.3b containment: disable seller-sensitive caching

export class ApiError extends Error {
  constructor({ status, code, message, detail, requestId, retryAfter }) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.detail = detail;
    this.requestId = requestId;
    this.retryAfter = retryAfter;
  }
}

function getErrorMessage(data, fallback) {
  if (!data) return fallback;
  if (typeof data.detail === "string") return data.detail;
  if (data.message) return data.message;
  if (data.error) return data.error;
  if (data.detail) return JSON.stringify(data.detail);
  return fallback;
}

function parseRetryAfter(header) {
  if (!header) return null;
  const secs = parseInt(header, 10);
  if (!isNaN(secs)) return secs;
  // Try date
  const date = Date.parse(header);
  if (!isNaN(date)) {
    return Math.max(0, Math.ceil((date - Date.now()) / 1000));
  }
  return null;
}

function isSensitiveEndpoint(endpoint) {
  // Any endpoint that returns seller-scoped data must be considered sensitive
  // Until proper session/principal epoch is available, we treat all /api as sensitive
  if (!endpoint) return true;
  if (endpoint.includes("/api/system/capabilities")) return true; // must be no-store per spec
  if (endpoint.startsWith("/api/")) return true;
  return false;
}

function getCached(key) {
  const entry = _cache[key];
  if (!entry) return null;
  // Epoch check: if epoch changed after cache write, entry is stale for new principal
  if (entry.epoch !== _sessionEpoch) {
    delete _cache[key];
    return null;
  }
  if (Date.now() - entry.timestamp > entry.ttl) {
    delete _cache[key];
    return null;
  }
  return entry.data;
}

function setCache(key, data, ttl = CACHE_TTL) {
  // Do not cache if epoch containment disabled for sensitive data
  if (!ENABLE_AUTH_CACHE) return;
  _cache[key] = { data, timestamp: Date.now(), ttl, epoch: _sessionEpoch };
}

function clearCache(prefix) {
  Object.keys(_cache).forEach((k) => {
    if (!prefix || k.startsWith(prefix)) delete _cache[k];
  });
}

// Exported: clears both in-memory cache and browser auth state, increments epoch
export function clearAuthStateAndCache() {
  _sessionEpoch++;
  Object.keys(_cache).forEach((k) => delete _cache[k]);
  if (typeof window !== "undefined") {
    try {
      localStorage.removeItem("jualin_token");
      localStorage.removeItem("jualin_user");
    } catch {}
    // Purge Cache Storage for dashboard/shell that might contain A data
    try {
      if (window.caches) {
        window.caches.keys().then((keys) => {
          keys.forEach((k) => {
            // Purge any jualin cache that could contain sensitive HTML/RSC
            if (k.toLowerCase().includes("jualin")) {
              window.caches.delete(k);
            }
          });
        });
      }
    } catch {}
    // Notify service worker to purge auth-sensitive caches
    try {
      if (navigator.serviceWorker && navigator.serviceWorker.controller) {
        navigator.serviceWorker.controller.postMessage({ type: "PURGE_AUTH_CACHE" });
      }
    } catch {}
  }
}

// ── Fetch wrapper with epoch-aware inflight guard + typed errors (P0.4) + P3.5 no Bearer ──
async function fetchAPI(endpoint, options = {}) {
  const requestEpoch = _sessionEpoch;

  const headers = {
    "Content-Type": "application/json",
    ...options.headers,
  };

  // CSRF for cookie-auth mutating requests — read csrf cookie and add header
  if (typeof document !== "undefined") {
    const method = (options.method || "GET").toUpperCase();
    if (["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
      try {
        const csrfCookie = document.cookie
          .split("; ")
          .find((c) => c.startsWith("jualin_csrf=") || c.startsWith("__Host-jualin_csrf="));
        if (csrfCookie) {
          const csrfValue = csrfCookie.split("=")[1];
          if (csrfValue && !headers["X-CSRF-Token"]) {
            headers["X-CSRF-Token"] = decodeURIComponent(csrfValue);
          }
        }
      } catch {}
    }
  }

  // Timeout handling via AbortController (30s default, overridable via options.timeout)
  const timeoutMs = options.timeout ?? 30000;
  const ctrl = new AbortController();
  const timeoutId = setTimeout(() => ctrl.abort(), timeoutMs);
  const signal = options.signal || ctrl.signal;

  let res;
  try {
    res = await fetch(`${API_BASE}${endpoint}`, {
      credentials: "include",
      ...options,
      headers,
      signal,
    });
  } catch (e) {
    clearTimeout(timeoutId);
    if (e.name === "AbortError") {
      throw new ApiError({
        status: 0,
        code: "timeout",
        message: "Request timeout",
        detail: null,
        requestId: null,
        retryAfter: null,
      });
    }
    // Network failure — do not treat as auth failure, allow caller to handle retry
    throw e;
  } finally {
    clearTimeout(timeoutId);
  }

  // Epoch changed during request? Old principal's response must not be applied to new principal
  if (requestEpoch !== _sessionEpoch) {
    throw new ApiError({
      status: 0,
      code: "session_changed",
      message: "Session changed during request",
      detail: null,
      requestId: null,
      retryAfter: null,
    });
  }

  // Extract request ID and retry-after headers for typed error
  const requestId = res.headers.get("X-Request-ID") || res.headers.get("x-request-id") || null;
  const retryAfter = parseRetryAfter(res.headers.get("Retry-After"));

  if (res.status === 401) {
    if (typeof window !== "undefined") {
      clearAuthStateAndCache();
      window.location.href = "/login";
    }
    throw new ApiError({
      status: 401,
      code: "authentication_required",
      message: "Session expired",
      detail: null,
      requestId,
      retryAfter,
    });
  }

  // 204 No Content — do not try to parse JSON
  if (res.status === 204) {
    if (requestEpoch !== _sessionEpoch) {
      throw new ApiError({
        status: 0,
        code: "session_changed",
        message: "Session changed during request",
        detail: null,
        requestId,
        retryAfter,
      });
    }
    return null;
  }

  // Try to parse JSON, but handle non-JSON gracefully (text/html error pages)
  let data;
  const contentType = res.headers.get("Content-Type") || "";
  if (contentType.includes("application/json")) {
    data = await res.json().catch(() => null);
  } else {
    // For non-JSON, try json first, fallback to text
    const text = await res.text().catch(() => "");
    try {
      data = text ? JSON.parse(text) : null;
    } catch {
      data = text ? { message: text.slice(0, 500) } : null;
    }
  }

  if (!res.ok) {
    const message = getErrorMessage(data, `Request failed with ${res.status}`);
    const code = (data && (data.error || data.code)) || `http_${res.status}`;
    throw new ApiError({
      status: res.status,
      code,
      message,
      detail: data?.detail ?? data ?? null,
      requestId,
      retryAfter,
    });
  }

  if (requestEpoch !== _sessionEpoch) {
    throw new ApiError({
      status: 0,
      code: "session_changed",
      message: "Session changed during request",
      detail: null,
      requestId,
      retryAfter,
    });
  }

  return data;
}

const apiFetch = fetchAPI;

// ── Cached fetch (for data that rarely changes) ──
// P0.3b: disabled for sensitive endpoints to prevent A->B leakage
async function fetchCached(endpoint, options = {}, ttl = CACHE_TTL) {
  // Sensitive endpoints bypass cache entirely (containment)
  if (isSensitiveEndpoint(endpoint) || !ENABLE_AUTH_CACHE) {
    return fetchAPI(endpoint, options);
  }
  const cacheKey = `api:${endpoint}:epoch:${_sessionEpoch}`;
  const cached = getCached(cacheKey);
  if (cached) return cached;

  const data = await fetchAPI(endpoint, options);
  // Only cache if epoch still same after fetch
  if (_sessionEpoch === (getCached(cacheKey)?.epoch ?? _sessionEpoch)) {
    setCache(cacheKey, data, ttl);
  }
  return data;
}

// ── File upload helper — P3.5: no Bearer, use HttpOnly cookies + CSRF ──
async function uploadFile(endpoint, file, extraData = {}) {
  const formData = new FormData();
  formData.append("file", file);
  Object.entries(extraData).forEach(([key, val]) =>
    formData.append(key, val)
  );

  // CSRF header for cookie-auth
  const csrfHeaders = {};
  if (typeof document !== "undefined") {
    try {
      const csrfCookie = document.cookie
        .split("; ")
        .find((c) => c.startsWith("jualin_csrf=") || c.startsWith("__Host-jualin_csrf="));
      if (csrfCookie) {
        csrfHeaders["X-CSRF-Token"] = decodeURIComponent(csrfCookie.split("=")[1]);
      }
    } catch {}
  }

  const res = await fetch(`${API_BASE}${endpoint}`, {
    method: "POST",
    credentials: "include",
    headers: {
      ...csrfHeaders,
      // Don't set Content-Type — browser sets it with boundary for FormData
    },
    body: formData,
  });

  if (res.status === 401) {
    if (typeof window !== "undefined") {
      clearAuthStateAndCache();
      window.location.href = "/login";
    }
    throw new Error("Session expired");
  }

  const data = await res.json().catch(() => null);

  if (!res.ok) {
    throw new Error(getErrorMessage(data, "Upload gagal"));
  }

  return data;
}

// Auth — boundary methods should clear cache on principal change
export const api = {
  // Auth — clear cache on principal change boundaries
  register: (body) => {
    clearAuthStateAndCache();
    return fetchAPI("/api/auth/register", { method: "POST", body: JSON.stringify(body) });
  },
  login: (body) => {
    clearAuthStateAndCache();
    return fetchAPI("/api/auth/login", { method: "POST", body: JSON.stringify(body) });
  },
  refreshAuth: () => fetchAPI("/api/auth/refresh", { method: "POST" }),
  logout: () => fetchAPI("/api/auth/logout", { method: "POST" }),
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
  getChatStats: (days = 30) =>
    fetchCached(`/api/analytics/chat-stats?days=${days}`, {}, 60000),
  getConversionFunnel: (days = 30) =>
    fetchCached(`/api/analytics/conversion-funnel?days=${days}`, {}, 60000),
  getSalesStages: (days = 30) =>
    fetchCached(`/api/analytics/sales-stages?days=${days}`, {}, 60000),

  // Admin
  getAdminStats: () => fetchAPI("/api/admin/stats"),
  getAdminSellers: () => fetchAPI("/api/admin/sellers"),
  updateAdminSeller: (id, body) =>
    fetchAPI(`/api/admin/sellers/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  getSystemHealth: () => fetchAPI("/api/admin/system"),
  getProviderHealth: () => fetchAPI("/api/admin/provider-health"),

  // Scale-up: integrations
  getIntegrations: () => fetchAPI("/api/integrations/"),
  getIntegrationHealth: () => fetchAPI("/api/integrations/health"),
  connectWhatsApp: (body) =>
    fetchAPI("/api/integrations/whatsapp/connect", { method: "POST", body: JSON.stringify(body) }),

  // Scale-up: inbox
  getInboxThreads: (params = "") => fetchAPI(`/api/inbox/threads${params}`),
  getInboxThread: (id) => fetchAPI(`/api/inbox/threads/${id}`),
  replyInboxThread: (id, body) =>
    fetchAPI(`/api/inbox/threads/${id}/reply`, { method: "POST", body: JSON.stringify(body) }),
  updateInboxThreadMode: (id, body) =>
    fetchAPI(`/api/inbox/threads/${id}/mode`, { method: "PATCH", body: JSON.stringify(body) }),
  submitInboxFeedback: (messageId, body) =>
    fetchAPI(`/api/inbox/messages/${messageId}/feedback`, { method: "PATCH", body: JSON.stringify(body) }),
  assignInboxCustomer: (threadId, body) =>
    fetchAPI(`/api/inbox/threads/${threadId}/assign-customer`, { method: "POST", body: JSON.stringify(body) }),

  // Scale-up: customers
  getCustomers: (q = "") => fetchAPI(`/api/customers/${q ? `?q=${encodeURIComponent(q)}` : ""}`),
  getCustomer: (id) => fetchAPI(`/api/customers/${id}`),
  updateCustomer: (id, body) =>
    fetchAPI(`/api/customers/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  getCustomerTimeline: (id) => fetchAPI(`/api/customers/${id}/timeline`),

  // Scale-up: AI quality
  getAITraces: (status = "") =>
    fetchAPI(`/api/ai-quality/traces${status ? `?status=${encodeURIComponent(status)}` : ""}`),
  createAIFeedback: (body) =>
    fetchAPI("/api/ai-quality/feedback", { method: "POST", body: JSON.stringify(body) }),
  getAIEvalCases: () => fetchAPI("/api/ai-quality/eval-cases"),
  runAIEval: () => fetchAPI("/api/ai-quality/evals/run", { method: "POST" }),

  // Scale-up: campaigns
  getCampaigns: () => fetchAPI("/api/campaigns/"),
  generateCampaign: (body) =>
    fetchAPI("/api/campaigns/generate", { method: "POST", body: JSON.stringify(body) }),
  updateCampaign: (id, body) =>
    fetchAPI(`/api/campaigns/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  previewCampaign: (id) => fetchAPI(`/api/campaigns/${id}/preview`, { method: "POST" }),
  sendCampaign: (id) => fetchAPI(`/api/campaigns/${id}/send`, { method: "POST" }),

  // Scale-up: workflows
  getWorkflowTemplates: () => fetchAPI("/api/workflows/templates"),
  getWorkflowRules: () => fetchAPI("/api/workflows/rules"),
  createWorkflowRule: (body) =>
    fetchAPI("/api/workflows/rules", { method: "POST", body: JSON.stringify(body) }),
  updateWorkflowRule: (id, body) =>
    fetchAPI(`/api/workflows/rules/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  getWorkflowRuns: () => fetchAPI("/api/workflows/runs"),
  getWorkflowRun: (id) => fetchAPI(`/api/workflows/runs/${id}`),

  // Scale-up: billing/import
  getBillingPlans: () => fetchAPI("/api/billing/plans"),
  getBillingUsage: () => fetchAPI("/api/billing/usage"),
  previewProductImport: (file) => uploadFile("/api/marketplace/products/preview", file),
  executeProductImport: (body) =>
    fetchAPI("/api/marketplace/products/import", { method: "POST", body: JSON.stringify(body) }),

  // Admin extra
  adminChangePlan: (sellerId, body) =>
    fetchAPI(`/api/billing/admin/sellers/${sellerId}/plan`, { method: "POST", body: JSON.stringify(body) }),
  adminOverrideQuota: (sellerId, body) =>
    fetchAPI(`/api/billing/admin/sellers/${sellerId}/override-quota`, { method: "POST", body: JSON.stringify(body) }),

  // Orders
  getOrderStats: () => fetchCached("/api/orders/stats", {}, 30000),
  getOrderHistory: (id) => fetchAPI(`/api/orders/${id}/history`),
  exportOrdersCsv: (status) =>
    `${API_BASE}/api/orders/export/csv${status ? `?status=${status}` : ""}`,

  // Payments
  createPayment: (body) =>
    fetchAPI("/api/payments/create", { method: "POST", body: JSON.stringify(body) }),
  getPaymentStatus: (orderId) =>
    fetchAPI(`/api/payments/status/${orderId}`),
  getPaymentMethods: () =>
    fetchCached("/api/payments/methods", {}, 300000),  // Cache 5 min
  getPaymentConfig: () =>
    fetchCached("/api/payments/config", {}, 300000),
  getPublicPaymentStatus: (orderId, token) =>
    fetchAPI(`/api/payments/public/status/${orderId}?token=${encodeURIComponent(token)}`),
  getPublicPaymentMethods: (orderId, token) =>
    fetchAPI(`/api/payments/public/methods/${orderId}?token=${encodeURIComponent(token)}`),
  createPublicPayment: (body) =>
    fetchAPI("/api/payments/public/create", { method: "POST", body: JSON.stringify(body) }),

  // ── P2.4 — Public capability session flow (fragment -> HttpOnly cookie) ──
  exchangePublicCapability: (orderId, bootstrapToken) =>
    fetchAPI(`/api/public/payments/${orderId}/exchange`, {
      method: "POST",
      body: JSON.stringify({ bootstrap_token: bootstrapToken }),
      credentials: "include",
    }),
  getPublicPaymentStatusViaSession: (orderId) =>
    fetchAPI(`/api/public/payments/${orderId}/status`, {
      method: "GET",
      credentials: "include",
    }),
  getPublicPaymentMethodsViaSession: (orderId) =>
    fetchAPI(`/api/public/payments/${orderId}/methods`, {
      method: "GET",
      credentials: "include",
    }),
  createPublicPaymentViaSession: (body) =>
    fetchAPI(`/api/public/payments/${body.order_id}/create-via-session`, {
      method: "POST",
      body: JSON.stringify(body),
      credentials: "include",
    }),
  grantReminderConsent: (orderId, granted, copyVersion) =>
    fetchAPI(`/api/public/payments/${orderId}/reminder-consent`, {
      method: "POST",
      body: JSON.stringify({ granted, copy_version: copyVersion }),
      credentials: "include",
    }),

  // Utility
  clearCache: () => clearCache(),

  // Plan B: Templates
  getTemplates: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return fetchAPI(`/api/templates/?${qs}`);
  },
  installTemplate: (id) => fetchAPI(`/api/templates/${id}/install`, { method: "POST" }),
  duplicateTemplate: (id) => fetchAPI(`/api/templates/${id}/duplicate`, { method: "POST" }),

  // Plan B: Onboarding
  getOnboarding: () => fetchAPI("/api/onboarding/"),
  updateOnboarding: (body) => fetchAPI("/api/onboarding/", { method: "PATCH", body: JSON.stringify(body) }),
  completeOnboarding: () => fetchAPI("/api/onboarding/complete", { method: "POST" }),
  onboardingTestChat: () => fetchAPI("/api/onboarding/test-chat", { method: "POST" }),

  // Plan B: Storefront
  getMyStorefront: () => fetchAPI("/api/storefront/"),
  updateStorefront: (body) => fetchAPI("/api/storefront/", { method: "PATCH", body: JSON.stringify(body) }),
  generateStorefront: () => fetchAPI("/api/storefront/generate", { method: "POST" }),

  // Plan B: Campaign recommendations
  getCampaignRecommendations: (status = "") =>
    fetchAPI(`/api/campaigns/recommendations${status ? `?status=${status}` : ""}`),
  createDraftFromRecommendation: (id) =>
    fetchAPI(`/api/campaigns/recommendations/${id}/create-draft`, { method: "POST" }),
  dismissRecommendation: (id) =>
    fetchAPI(`/api/campaigns/recommendations/${id}/dismiss`, { method: "POST" }),

  // Plan B: Analytics extras
  getRevenue: (period = "30d") => fetchAPI(`/api/analytics/revenue?period=${period}`),
  getCampaignROI: (campaignId = 0) => fetchAPI(`/api/analytics/campaign-roi?campaign_id=${campaignId}`),
  getProductInsights: () => fetchAPI("/api/analytics/product-insights"),
  aiEnrichProduct: (id) => fetchAPI(`/api/products/${id}/ai-enrich`, { method: "POST" }),

  // ── Market Acceptance: Sprint 1 — Quick-Start Onboarding ──
  quickStartOnboarding: (body) =>
    fetchAPI("/api/onboarding/quick-start", { method: "POST", body: JSON.stringify(body) }),
  createSampleProducts: (body) =>
    fetchAPI("/api/onboarding/sample-products", { method: "POST", body: JSON.stringify(body) }),
  simulateChat: (body) =>
    fetchAPI("/api/onboarding/simulate-chat", { method: "POST", body: JSON.stringify(body) }),

  // ── Market Acceptance: Sprint 2 — Template Niche ──
  getTemplateNiches: () => fetchAPI("/api/templates/niches"),
  getRecommendedTemplates: (niche) => fetchAPI(`/api/templates/recommended?niche=${niche}`),
  installTemplatePack: (body) =>
    fetchAPI("/api/templates/install-pack", { method: "POST", body: JSON.stringify(body) }),

  // ── Market Acceptance: Sprint 5 — Money Dashboard ──
  getMoneyDashboard: () => fetchCached("/api/analytics/money", {}, 30000),
  getAIImpact: () => fetchCached("/api/analytics/ai-impact", {}, 60000),
  getRecoveryStats: () => fetchCached("/api/analytics/recovery", {}, 60000),

  // ── P2.6 — Recovery observe-only ──
  getCapabilities: () => fetchAPI("/api/system/capabilities", { method: "GET" }),
  getRecoveryOverview: () => fetchAPI("/api/recovery/overview"),
  getRecoveryOpportunities: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return fetchAPI(`/api/recovery/opportunities?${qs}`);
  },
  getRecoveryOpportunity: (id) => fetchAPI(`/api/recovery/opportunities/${id}`),
  approveRecoveryOpportunity: (id, body) =>
    fetchAPI(`/api/recovery/opportunities/${id}/approve`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  rejectRecoveryOpportunity: (id, body) =>
    fetchAPI(`/api/recovery/opportunities/${id}/reject`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  // ── P6.3 — Proof Mode (admin/demo) ──
  getProofCapability: () => fetchAPI("/api/proof/capability"),
  runProofMode: (body = {}) =>
    fetchAPI("/api/proof/run", { method: "POST", body: JSON.stringify(body) }),
  getProofLatest: () => fetchAPI("/api/proof/latest"),

  // ── Market Acceptance: Sprint 6 — Trust Layer ──
  getTrustProfile: () => fetchAPI("/api/trust-profile"),
  updateTrustProfile: (body) =>
    fetchAPI("/api/trust-profile", { method: "PATCH", body: JSON.stringify(body) }),
  getPublicTrustProfile: (slug) => fetchAPI(`/api/public/trust-profile/${slug}`),

  // ── Market Acceptance: Sprint 3 — Growth Links ──
  createGrowthLink: (body) =>
    fetchAPI("/api/growth-links", { method: "POST", body: JSON.stringify(body) }),
  getGrowthLinks: () => fetchAPI("/api/growth-links"),
  getGrowthLinkStats: () => fetchAPI("/api/growth-links/stats"),

  // ── Market Acceptance: Sprint 4 — WA Templates ──
  generateWATemplate: (body) =>
    fetchAPI("/api/whatsapp/templates/generate", { method: "POST", body: JSON.stringify(body) }),
  getWATemplates: () => fetchAPI("/api/whatsapp/templates"),
  submitWATemplate: (id) =>
    fetchAPI(`/api/whatsapp/templates/${id}/submit`, { method: "POST" }),
  syncWATemplateStatus: (id) =>
    fetchAPI(`/api/whatsapp/templates/${id}/sync-status`, { method: "POST" }),

  // ── Market Acceptance: Sprint 7 — Referral Rewards ──
  getMyReferralLink: () => fetchAPI("/api/referrals/my-link"),
  claimReferralReward: (body) =>
    fetchAPI("/api/referrals/claim", { method: "POST", body: JSON.stringify(body) }),
  getReferralRewards: () => fetchAPI("/api/referrals/rewards"),

  // ── Market Acceptance: Sprint 8 — Concierge ──
  startConcierge: (sellerId) =>
    fetchAPI(`/api/admin/sellers/${sellerId}/concierge-start`, { method: "POST" }),
  updateSetupChecklist: (sellerId, body) =>
    fetchAPI(`/api/admin/sellers/${sellerId}/setup-checklist`, { method: "PATCH", body: JSON.stringify(body) }),
  getImpersonationToken: (sellerId) =>
    fetchAPI(`/api/admin/sellers/${sellerId}/impersonation-token`, { method: "POST" }),

  // ── JUALIN OS: Agent OS / AI Crew ──
  agentOsOverview: () => fetchAPI("/api/agent-os/overview"),
  agentOsActivity: (limit = 30) => fetchAPI(`/api/agent-os/activity?limit=${limit}`),
  agentOsBrief: () => fetchAPI("/api/agent-os/brief"),
  agentOsGetPolicy: () => fetchAPI("/api/agent-os/policy"),
  agentOsUpdatePolicy: (body) =>
    fetchAPI("/api/agent-os/policy", { method: "PATCH", body: JSON.stringify(body) }),
  agentOsApprovals: (status = "pending") =>
    fetchAPI(`/api/agent-os/approvals?status=${status}`),
  agentOsApprove: (id) =>
    fetchAPI(`/api/agent-os/approvals/${id}/approve`, { method: "POST" }),
  agentOsReject: (id) =>
    fetchAPI(`/api/agent-os/approvals/${id}/reject`, { method: "POST" }),
  agentOsNegotiations: () => fetchAPI("/api/agent-os/negotiations"),
  agentOsImpact: () => fetchAPI("/api/agent-os/impact"),

  // ── Admin: LLM Control Panel ──
  adminLlmGet: () => fetchAPI("/api/admin/llm-settings"),
  adminLlmUpdate: (body) =>
    fetchAPI("/api/admin/llm-settings", { method: "PUT", body: JSON.stringify(body) }),
  adminLlmAddKey: (key) =>
    fetchAPI("/api/admin/llm-settings/keys", { method: "POST", body: JSON.stringify({ key }) }),
  adminLlmRemoveKey: (index) =>
    fetchAPI(`/api/admin/llm-settings/keys/${index}`, { method: "DELETE" }),
  adminLlmTest: () =>
    fetchAPI("/api/admin/llm-settings/test", { method: "POST", body: JSON.stringify({}) }),
};


// ── SSE Streaming Chat Helper ──

/**
 * Send a chat message and receive streaming AI response via SSE.
 * 
 * @param {Object} body - {message, session_id, seller_slug}
 * @param {Function} onToken - Called for each token: (token: string) => void
 * @param {Function} onMetadata - Called once with metadata: ({intent, stage}) => void
 * @param {Function} onDone - Called when stream completes: ({full_response, intent, stage, session_id}) => void
 * @param {Function} onError - Called on error: (error: Error) => void
 * @returns {Function} abort - Call this to cancel the stream
 */
export function sendChatStream({ body, onToken, onMetadata, onNego, onDone, onError }) {
  const controller = new AbortController();

  (async () => {
    try {
      const res = await fetch(`${API_BASE}/api/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP ${res.status}`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // Parse SSE events from buffer
        const lines = buffer.split("\n");
        buffer = lines.pop() || ""; // Keep incomplete line in buffer

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const jsonStr = line.slice(6).trim();
          if (!jsonStr) continue;

          try {
            const event = JSON.parse(jsonStr);

            if (event.type === "metadata" && onMetadata) {
              onMetadata(event);
            } else if (event.type === "token" && onToken) {
              onToken(event.token);
            } else if (event.type === "nego" && onNego) {
              onNego(event);
            } else if (event.type === "done" && onDone) {
              onDone(event);
            }
          } catch (parseErr) {
            // Skip malformed events
            console.warn("SSE parse error:", parseErr);
          }
        }
      }
    } catch (err) {
      if (err.name !== "AbortError") {
        if (onError) onError(err);
        else console.error("Stream error:", err);
      }
    }
  })();

  // Return abort function
  return () => controller.abort();
}

// ══════════════════════════════════════════════════
// Plan A: Admin endpoints
// ══════════════════════════════════════════════════

export async function adminListJobs(params = {}) {
  const qs = new URLSearchParams(params).toString();
  return apiFetch(`/api/admin/jobs?${qs}`);
}

export async function adminRetryJob(jobId) {
  return apiFetch(`/api/admin/jobs/${jobId}/retry`, { method: "POST" });
}

export async function adminReplayWebhook(eventId) {
  return apiFetch(`/api/admin/webhooks/${eventId}/replay`, { method: "POST" });
}

export async function adminListAuditLogs(params = {}) {
  const qs = new URLSearchParams(params).toString();
  return apiFetch(`/api/admin/audit-logs?${qs}`);
}

export async function adminGetSecurityEvents(params = {}) {
  const qs = new URLSearchParams(params).toString();
  return apiFetch(`/api/admin/security-events?${qs}`);
}

// ══════════════════════════════════════════════════
// Plan A: Inbox productization
// ══════════════════════════════════════════════════

export async function inboxManageLabel(threadId, label, action = "add") {
  return apiFetch(`/api/inbox/threads/${threadId}/labels`, {
    method: "POST",
    body: JSON.stringify({ label, action }),
  });
}

export async function inboxAddNote(threadId, content) {
  return apiFetch(`/api/inbox/threads/${threadId}/notes`, {
    method: "POST",
    body: JSON.stringify({ content }),
  });
}

export async function inboxListNotes(threadId) {
  return apiFetch(`/api/inbox/threads/${threadId}/notes`);
}

export async function listCannedReplies() {
  return apiFetch("/api/inbox/canned-replies");
}

export async function createCannedReply(data) {
  return apiFetch("/api/inbox/canned-replies", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

// ══════════════════════════════════════════════════
// Plan A: Workflow dry-run
// ══════════════════════════════════════════════════

export async function workflowDryRun(ruleId) {
  return apiFetch(`/api/workflows/rules/${ruleId}/dry-run`, { method: "POST" });
}

// ══════════════════════════════════════════════════
// Plan A: AI Quality prompts
// ══════════════════════════════════════════════════

export async function listPrompts() {
  return apiFetch("/api/ai-quality/prompts");
}

// ══════════════════════════════════════════════════
// Plan B: Templates
// ══════════════════════════════════════════════════

export async function getTemplates(params = {}) {
  const qs = new URLSearchParams(params).toString();
  return apiFetch(`/api/templates/?${qs}`);
}

export async function installTemplate(templateId) {
  return apiFetch(`/api/templates/${templateId}/install`, { method: "POST" });
}

export async function duplicateTemplate(templateId) {
  return apiFetch(`/api/templates/${templateId}/duplicate`, { method: "POST" });
}

// ══════════════════════════════════════════════════
// Plan B: Onboarding
// ══════════════════════════════════════════════════

export async function getOnboarding() {
  return apiFetch("/api/onboarding/");
}

export async function updateOnboarding(data) {
  return apiFetch("/api/onboarding/", { method: "PATCH", body: JSON.stringify(data) });
}

export async function completeOnboarding() {
  return apiFetch("/api/onboarding/complete", { method: "POST" });
}

export async function onboardingTestChat() {
  return apiFetch("/api/onboarding/test-chat", { method: "POST" });
}

// ══════════════════════════════════════════════════
// Plan B: Storefront
// ══════════════════════════════════════════════════

export async function getMyStorefront() {
  return apiFetch("/api/storefront/");
}

export async function updateStorefront(data) {
  return apiFetch("/api/storefront/", { method: "PATCH", body: JSON.stringify(data) });
}

export async function generateStorefront() {
  return apiFetch("/api/storefront/generate", { method: "POST" });
}

export async function updateStorefrontSection(sectionId, data) {
  return apiFetch(`/api/storefront/sections/${sectionId}`, { method: "PATCH", body: JSON.stringify(data) });
}

// ══════════════════════════════════════════════════
// Plan B: Campaign Recommendations
// ══════════════════════════════════════════════════

export async function getCampaignRecommendations(status = "") {
  return apiFetch(`/api/campaigns/recommendations${status ? `?status=${status}` : ""}`);
}

export async function createDraftFromRecommendation(recId) {
  return apiFetch(`/api/campaigns/recommendations/${recId}/create-draft`, { method: "POST" });
}

export async function dismissRecommendation(recId) {
  return apiFetch(`/api/campaigns/recommendations/${recId}/dismiss`, { method: "POST" });
}

// ══════════════════════════════════════════════════
// Plan B: Analytics extras
// ══════════════════════════════════════════════════

export async function getRevenue(period = "30d") {
  return apiFetch(`/api/analytics/revenue?period=${period}`);
}

export async function getCampaignROI(campaignId = 0) {
  return apiFetch(`/api/analytics/campaign-roi?campaign_id=${campaignId}`);
}

export async function getProductInsights() {
  return apiFetch("/api/analytics/product-insights");
}

export async function aiEnrichProduct(productId) {
  return apiFetch(`/api/products/${productId}/ai-enrich`, { method: "POST" });
}

// ══════════════════════════════════════════════════
// Plan C: Referrals
// ══════════════════════════════════════════════════
export async function createReferralCode(data) {
  return apiFetch("/api/referrals/codes", { method: "POST", body: JSON.stringify(data) });
}
export async function listReferralCodes() { return apiFetch("/api/referrals/codes"); }
export async function getReferralSummary() { return apiFetch("/api/referrals/summary"); }
export async function listResellers() { return apiFetch("/api/referrals/resellers"); }

// ══════════════════════════════════════════════════
// Plan C: Lead Capture
// ══════════════════════════════════════════════════
export async function createLeadForm(data) {
  return apiFetch("/api/lead-forms/", { method: "POST", body: JSON.stringify(data) });
}
export async function listLeadForms() { return apiFetch("/api/lead-forms/"); }
export async function listLeadSubmissions(status = "") {
  return apiFetch(`/api/lead-forms/submissions${status ? `?status=${status}` : ""}`);
}

// ══════════════════════════════════════════════════
// Plan C: Sales Playbooks
// ══════════════════════════════════════════════════
export async function listPlaybooks() { return apiFetch("/api/ai/playbooks"); }
export async function updatePlaybook(id, data) {
  return apiFetch(`/api/ai/playbooks/${id}`, { method: "PATCH", body: JSON.stringify(data) });
}

// ══════════════════════════════════════════════════
// Plan C: Customer Scoring
// ══════════════════════════════════════════════════
export async function getCustomerScore(customerId) {
  return apiFetch(`/api/ai/customers/${customerId}/score`);
}
export async function recomputeScores() {
  return apiFetch("/api/ai/customers/recompute-scores", { method: "POST" });
}

// ══════════════════════════════════════════════════
// Plan C: Offers
// ══════════════════════════════════════════════════
export async function createOffer(data) {
  return apiFetch("/api/ai/offers", { method: "POST", body: JSON.stringify(data) });
}
export async function listOffers() { return apiFetch("/api/ai/offers"); }
export async function listOfferRecommendations() { return apiFetch("/api/ai/offers/recommendations"); }
export async function approveOfferRec(id) {
  return apiFetch(`/api/ai/offers/recommendations/${id}/approve`, { method: "POST" });
}

// ══════════════════════════════════════════════════
// Plan C: Knowledge Base
// ══════════════════════════════════════════════════
export async function createKnowledgeSource(data) {
  return apiFetch("/api/ai/knowledge/sources", { method: "POST", body: JSON.stringify(data) });
}
export async function listKnowledgeSources() { return apiFetch("/api/ai/knowledge/sources"); }
export async function reindexKnowledge(sourceId) {
  return apiFetch(`/api/ai/knowledge/sources/${sourceId}/reindex`, { method: "POST" });
}
export async function deleteKnowledge(sourceId) {
  return apiFetch(`/api/ai/knowledge/sources/${sourceId}`, { method: "DELETE" });
}

// ══════════════════════════════════════════════════
// Plan C: QA Review
// ══════════════════════════════════════════════════
export async function listQAReviews(status = "pending") {
  return apiFetch(`/api/ai/qa-review?status=${status}`);
}
export async function approveQA(id, data = {}) {
  return apiFetch(`/api/ai/qa-review/${id}/approve`, { method: "POST", body: JSON.stringify(data) });
}
export async function rejectQA(id, data = {}) {
  return apiFetch(`/api/ai/qa-review/${id}/reject`, { method: "POST", body: JSON.stringify(data) });
}
export async function editAndSendQA(id, data) {
  return apiFetch(`/api/ai/qa-review/${id}/edit-and-send`, { method: "POST", body: JSON.stringify(data) });
}

// ══════════════════════════════════════════════════
// Plan C: Experiments
// ══════════════════════════════════════════════════
export async function createExperiment(data) {
  return apiFetch("/api/ai/experiments", { method: "POST", body: JSON.stringify(data) });
}
export async function listExperiments() { return apiFetch("/api/ai/experiments"); }
export async function startExperiment(id) {
  return apiFetch(`/api/ai/experiments/${id}/start`, { method: "POST" });
}
export async function stopExperiment(id) {
  return apiFetch(`/api/ai/experiments/${id}/stop`, { method: "POST" });
}
export async function getExperimentResults(id) {
  return apiFetch(`/api/ai/experiments/${id}/results`);
}
