import { describe, it, expect, vi, beforeEach } from 'vitest';

const mockFetch = vi.fn();
global.fetch = mockFetch;

const mockHeaders = (contentType = 'application/json', extra = {}) => ({
  get: (name) => {
    const lower = name.toLowerCase();
    if (lower === 'content-type') return contentType;
    if (lower === 'x-request-id') return extra.requestId || 'req-123';
    if (lower === 'retry-after') return extra.retryAfter || null;
    return null;
  },
});

describe('ApiError typed failures (P0.4)', () => {
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

  it('preserves 400 envelope code', async () => {
    const { api, ApiError } = await import('./api.js');
    mockFetch.mockResolvedValue({
      ok: false,
      status: 400,
      headers: mockHeaders('application/json', { requestId: 'req-400' }),
      json: async () => ({ error: 'invalid_transition', message: 'Bad', detail: { current_version: 5 } }),
      text: async () => '',
    });
    global.localStorage.setItem('jualin_token', 'tok');
    try {
      await api.getMe();
      expect.fail('should throw');
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError);
      expect(e.status).toBe(400);
      expect(e.code).toBe('invalid_transition');
      expect(e.requestId).toBe('req-400');
    }
  });

  it('handles 204 empty body', async () => {
    const { api } = await import('./api.js');
    mockFetch.mockResolvedValue({
      ok: true,
      status: 204,
      headers: mockHeaders(),
      json: async () => { throw new Error('no json'); },
      text: async () => '',
    });
    global.localStorage.setItem('jualin_token', 'tok');
    const result = await api.getMe();
    expect(result).toBeNull();
  });

  it('handles 429 with Retry-After', async () => {
    const { api, ApiError } = await import('./api.js');
    mockFetch.mockResolvedValue({
      ok: false,
      status: 429,
      headers: mockHeaders('application/json', { retryAfter: '120', requestId: 'req-429' }),
      json: async () => ({ error: 'rate_limited', message: 'Too many' }),
      text: async () => '',
    });
    global.localStorage.setItem('jualin_token', 'tok');
    try {
      await api.getMe();
      expect.fail('should throw');
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError);
      expect(e.status).toBe(429);
      expect(e.retryAfter).toBe(120);
    }
  });

  it('handles non-JSON error (html)', async () => {
    const { api, ApiError } = await import('./api.js');
    mockFetch.mockResolvedValue({
      ok: false,
      status: 500,
      headers: mockHeaders('text/html'),
      json: async () => { throw new Error('not json'); },
      text: async () => '<html>Server Error</html>',
    });
    global.localStorage.setItem('jualin_token', 'tok');
    try {
      await api.getMe();
      expect.fail('should throw');
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError);
      expect(e.status).toBe(500);
      expect(e.message).toBeTruthy();
    }
  });

  it('timeout throws ApiError', async () => {
    const { api, ApiError } = await import('./api.js');
    mockFetch.mockImplementation(() => {
      const err = new Error('aborted');
      err.name = 'AbortError';
      return Promise.reject(err);
    });
    global.localStorage.setItem('jualin_token', 'tok');
    try {
      await api.getMe();
      expect.fail('should throw');
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError);
      expect(e.code).toBe('timeout');
    }
  });
});
