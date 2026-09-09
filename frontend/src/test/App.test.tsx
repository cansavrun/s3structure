import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';
import { App } from '../App';

describe('session lifecycle', () => {
  it('renders login after initial 401, enters workspace, and clears file cache on logout', async () => {
    const me = {
      customer: { id: 'amy', name: 'Amy Energy' },
      key_name: 'Operator',
      expires_at: '',
      preview_max_bytes: 1000,
    };
    let authenticated = false;
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (url, init) => {
      if (url === '/api/auth/login') {
        authenticated = true;
        return new Response('{}');
      }
      if (url === '/api/auth/logout') {
        authenticated = false;
        return new Response(null, { status: 204 });
      }
      if (url === '/api/me')
        return new Response(JSON.stringify(authenticated ? me : {}), {
          status: authenticated ? 200 : 401,
        });
      if (init?.signal?.aborted) throw new DOMException('Aborted', 'AbortError');
      return new Response(JSON.stringify({ folders: [], files: [], path: '', next_cursor: null }));
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const user = userEvent.setup();
    render(
      <QueryClientProvider client={client}>
        <App />
      </QueryClientProvider>,
    );
    await user.type(await screen.findByLabelText('API anahtarınız'), 'sample-key');
    await user.click(screen.getByRole('button', { name: 'Güvenli giriş yap' }));
    expect(
      await screen.findByRole('heading', { name: 'Her şey yerli yerinde.' }),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(client.getQueryCache().findAll({ queryKey: ['files'] }).length).toBeGreaterThan(0),
    );
    await user.click(screen.getByRole('button', { name: 'Güvenli çıkış' }));
    expect(await screen.findByLabelText('API anahtarınız')).toBeInTheDocument();
    expect(client.getQueryCache().findAll({ queryKey: ['files'] })).toHaveLength(0);
  });
});
