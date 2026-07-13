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

    // After 401, token should be cleared and cache cleared
    expect(global.localStorage.getItem('jualin_token')).toBeNull();
    expect(global.localStorage.getItem('jualin_user')).toBeNull();

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
