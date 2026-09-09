import { describe, expect, it, vi } from 'vitest';
import { api, downloadUrl } from '../api';

describe('API boundary', () => {
  it('encodes relative paths instead of concatenating URL parameters', () => {
    expect(downloadUrl('a&customer=atlas.csv')).toBe(
      '/api/files/download?path=a%26customer%3Datlas.csv',
    );
  });
  it('announces expired sessions so all customer cache is cleared', async () => {
    const listener = vi.fn();
    window.addEventListener('tenantfiles:unauthorized', listener);
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{}', { status: 401 }));
    await expect(api('/files')).rejects.toMatchObject({ status: 401 });
    expect(listener).toHaveBeenCalledOnce();
    window.removeEventListener('tenantfiles:unauthorized', listener);
  });
});
