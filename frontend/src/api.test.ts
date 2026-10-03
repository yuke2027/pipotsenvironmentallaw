import { afterEach, describe, expect, it, vi } from 'vitest';
import { api, ApiError, queryString } from './api';

afterEach(() => { vi.unstubAllGlobals(); document.cookie = 'esp_csrf=; Max-Age=0; path=/'; });
describe('authenticated API client', () => {
  it('sends CSRF with same-origin credentials and preserves multipart boundaries', async () => {
    document.cookie = 'esp_csrf=abc123; path=/';
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: 1 }), { status: 201 }));
    vi.stubGlobal('fetch', fetch);
    const form = new FormData(); form.append('file', new Blob(['evidence']), 'evidence.txt');
    await api('/attachments', { method: 'POST', body: form });
    expect(fetch.mock.calls[0][0]).toBe('/api/v2/attachments');
    expect(fetch.mock.calls[0][1].credentials).toBe('same-origin');
    expect(fetch.mock.calls[0][1].headers.get('X-CSRF-Token')).toBe('abc123');
    expect(fetch.mock.calls[0][1].headers.has('Content-Type')).toBe(false);
  });
  it('preserves permission failures and correlation IDs', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: { message: '没有权限' }, request_id: 'request-1' }), { status: 403 })));
    await expect(api('/enterprises')).rejects.toMatchObject({ status: 403, requestId: 'request-1', message: '没有权限' });
  });
  it('encodes filter values and omits absent parameters', () => {
    expect(queryString({ pollutant: 'PM2.5', q: '站点 甲', page_number: 1, missing: undefined })).toBe('pollutant=PM2.5&q=%E7%AB%99%E7%82%B9+%E7%94%B2&page_number=1');
  });
});
