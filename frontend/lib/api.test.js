import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock fetch globally
const mockFetch = vi.fn();
global.fetch = mockFetch;

describe('BUG-025 tenant cache isolation (P0.3b)', () => {
  beforeEach(() => {
    vi.resetModules();
    mockFetch.mockReset();
    // Clear localStorage
    if (typeof window !== 'undefined') {
      window.localStorage.clear();
    } else {
      global.localStorage = {
        store: {},
        getItem(k) { return this.store[k] || null; },
        setItem(k, v) { this.store[k] = v; },
        removeItem(k) { delete this.store[k]; },
        clear() { this.store = {}; },
      };
    }
  });

  const mockHeaders = (contentType = 'application/json') => ({
    get: (name) => {
      if (name.toLowerCase() === 'content-type') return contentType;
      return null;
    },
  });

  it('A->logout->B does not leak cached data', async () => {
    // Import fresh module to reset epoch and cache
    const { api, clearAuthStateAndCache } = await import('./api.js');

    // Mock A data
    const dataA = { quota: 100, user: 'A' };
    const dataB = { quota: 5, user: 'B' };

    mockFetch.mockImplementation((url) => {
      return Promise.resolve({
        ok: true,
        status: 200,
        headers: mockHeaders(),
        json: async () => dataA,
      });
    });

    // Simulate login A
    global.localStorage.setItem('jualin_token', 'token-A');
    // First call as A
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: mockHeaders(),
      json: async () => dataA,
    });
    const resultA = await api.getQuota();
    expect(resultA).toEqual(dataA);

    // Logout — should clear cache and epoch
    clearAuthStateAndCache();

    // Login B
    global.localStorage.setItem('jualin_token', 'token-B');
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: mockHeaders(),
      json: async () => dataB,
    });
    const resultB = await api.getQuota();
    expect(resultB).toEqual(dataB);
    expect(resultB).not.toEqual(dataA);
    expect(resultB.user).toBe('B');
  });

  it('response that finishes after epoch change is discarded', async () => {
    const { api, clearAuthStateAndCache } = await import('./api.js');

    const dataA = { summary: 'A' };

    // Simulate slow response for A
    let resolveSlow;
    const slowPromise = new Promise((resolve) => {
      resolveSlow = () => resolve({
        ok: true,
        status: 200,
        headers: mockHeaders(),
        json: async () => dataA,
      });
    });

    global.localStorage.setItem('jualin_token', 'token-A');
    mockFetch.mockReturnValueOnce(slowPromise);

    const fetchPromise = api.getSummary().catch((e) => e.message);

    // Before slow response resolves, logout and epoch changes
    clearAuthStateAndCache();
    global.localStorage.setItem('jualin_token', 'token-B');

    // Now resolve slow A response
    resolveSlow();

    const result = await fetchPromise;
    // Should throw "Session changed" error, not return A data
    expect(result).toMatch(/Session changed/);
  });

  it('terminal 401 clears cache', async () => {
    const { api, clearAuthStateAndCache } = await import('./api.js');

    global.localStorage.setItem('jualin_token', 'token-A');
    global.localStorage.setItem('jualin_user', JSON.stringify({ id: 1 }));

    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 401,
      headers: mockHeaders(),
      json: async () => ({ detail: 'expired' }),
    });

    // Mock window.location.href to avoid navigation error
    const originalLocation = global.window?.location;
    if (typeof window !== 'undefined') {
      delete window.location;
      window.location = { href: '' };
    } else {
      global.window = { localStorage: global.localStorage, location: { href: '' }, caches: { keys: async () => [] } };
    }

    try {
      await api.getMe();
    } catch (e) {
      expect(e.message).toMatch(/Session expired/);
    }

    // Session probes clear stale state without redirecting /login back to itself.
    expect(global.localStorage.getItem('jualin_token')).toBeNull();
    expect(global.localStorage.getItem('jualin_user')).toBeNull();
    expect(window.location.href).toBe('');

    if (originalLocation) {
      window.location = originalLocation;
    }
  });


  it('public capability 401 stays local and preserves seller auth state', async () => {
    const { api } = await import('./api.js');

    global.localStorage.setItem('jualin_token', 'token-A');
    global.localStorage.setItem('jualin_user', JSON.stringify({ id: 1 }));
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 401,
      headers: mockHeaders(),
      json: async () => ({ detail: { error: 'capability_required' } }),
    });

    const originalLocation = global.window?.location;
    if (typeof window !== 'undefined') {
      delete window.location;
      window.location = { href: '/pay/42' };
    } else {
      global.window = {
        localStorage: global.localStorage,
        location: { href: '/pay/42' },
        caches: { keys: async () => [] },
      };
    }

    await expect(api.getPublicPaymentStatusViaSession(42)).rejects.toMatchObject({
      status: 401,
    });
    expect(global.localStorage.getItem('jualin_token')).toBe('token-A');
    expect(global.localStorage.getItem('jualin_user')).not.toBeNull();
    expect(window.location.href).toBe('/pay/42');

    if (originalLocation) {
      window.location = originalLocation;
    }
  });

  it('capability endpoint is not cached', async () => {
    const mod = await import('./api.js');
    mockFetch.mockResolvedValue({
      ok: true,
      status: 200,
      headers: mockHeaders(),
      json: async () => ({ ok: true }),
    });

    const { api } = mod;
    global.localStorage.setItem('jualin_token', 'token');

    await api.getQuota();
    await api.getQuota();

    // Since cache disabled, fetch should be called twice
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });
});

describe('in-flight GET coalescing', () => {
  beforeEach(() => {
    vi.resetModules();
    mockFetch.mockReset();
    global.localStorage = {
      store: {},
      getItem(k) { return this.store[k] || null; },
      setItem(k, v) { this.store[k] = v; },
      removeItem(k) { delete this.store[k]; },
      clear() { this.store = {}; },
    };
    global.window = {
      localStorage: global.localStorage,
      location: { href: '' },
      caches: { keys: async () => [] },
    };
    global.navigator = { serviceWorker: { controller: null } };
  });

  const jsonHeaders = {
    get: (name) => (name.toLowerCase() === 'content-type' ? 'application/json' : null),
  };

  // Resolvable response so both callers are still pending when the second starts.
  function deferredResponse(body) {
    let release;
    const promise = new Promise((resolve) => {
      release = () => resolve({
        ok: true,
        status: 200,
        headers: jsonHeaders,
        json: async () => body,
      });
    });
    return { promise, release };
  }

  it('two concurrent GETs to the same endpoint issue one fetch', async () => {
    const { api } = await import('./api.js');
    const { promise, release } = deferredResponse({ items: [1] });
    mockFetch.mockReturnValue(promise);

    const first = api.getProducts();
    const second = api.getProducts();

    release();
    const [a, b] = await Promise.all([first, second]);

    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(a).toBe(b);
  });

  it('different endpoints are not coalesced', async () => {
    const { api } = await import('./api.js');
    const { promise, release } = deferredResponse({ ok: true });
    mockFetch.mockReturnValue(promise);

    const both = Promise.all([api.getProducts(), api.getOrders()]);
    release();
    await both;

    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  it('two concurrent POSTs issue two fetches', async () => {
    const { api } = await import('./api.js');
    const { promise, release } = deferredResponse({ id: 1 });
    mockFetch.mockReturnValue(promise);

    const both = Promise.all([
      api.sendChat({ message: 'hi' }),
      api.sendChat({ message: 'hi' }),
    ]);
    release();
    await both;

    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  it('a rejected shared GET reaches every caller and is not reused', async () => {
    const { api } = await import('./api.js');

    let rejectFirst;
    mockFetch.mockReturnValueOnce(new Promise((_, reject) => { rejectFirst = reject; }));

    const first = api.getProducts();
    const second = api.getProducts();
    rejectFirst(new Error('network down'));

    await expect(first).rejects.toThrow('network down');
    await expect(second).rejects.toThrow('network down');
    expect(mockFetch).toHaveBeenCalledTimes(1);

    // Failed entry evicted — the retry hits the network again.
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: jsonHeaders,
      json: async () => ({ items: [] }),
    });
    await expect(api.getProducts()).resolves.toEqual({ items: [] });
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  it('clearAuthStateAndCache drops in-flight GETs so a new principal never shares them', async () => {
    const { api, clearAuthStateAndCache } = await import('./api.js');

    const dataA = { user: 'A' };
    const dataB = { user: 'B' };
    const first = deferredResponse(dataA);
    mockFetch.mockReturnValueOnce(first.promise);

    const staleCall = api.getProducts().catch((e) => e.code);

    clearAuthStateAndCache();

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: jsonHeaders,
      json: async () => dataB,
    });
    const freshCall = api.getProducts();

    first.release();

    expect(await staleCall).toBe('session_changed');
    expect(await freshCall).toEqual(dataB);
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });
});
