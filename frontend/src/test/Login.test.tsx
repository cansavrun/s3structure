import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { Login } from '../components/Login';

describe('API key login', () => {
  it('exchanges key for session and clears key without persistent storage', async () => {
    const user = userEvent.setup();
    const onLogin = vi.fn();
    const fetcher = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response('{}', { status: 200 }))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ customer: { id: 'amy', name: 'Amy' } }), { status: 200 }),
      );
    const storage = vi.spyOn(Storage.prototype, 'setItem');
    render(<Login onLogin={onLogin} />);
    await user.type(screen.getByLabelText('API anahtarınız'), 'secret-key');
    await user.click(screen.getByRole('button', { name: 'Güvenli giriş yap' }));
    expect(fetcher.mock.calls[0][1]?.body).toBe(JSON.stringify({ api_key: 'secret-key' }));
    expect(fetcher.mock.calls[0][1]?.credentials).toBe('same-origin');
    expect(screen.getByLabelText('API anahtarınız')).toHaveValue('');
    expect(storage).not.toHaveBeenCalled();
    expect(onLogin).toHaveBeenCalledWith({ customer: { id: 'amy', name: 'Amy' } });
  });

  it('shows authentication errors and clears the attempted key', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Anahtar geçersiz' }), { status: 401 }),
    );
    const user = userEvent.setup();
    render(<Login onLogin={vi.fn()} />);
    await user.type(screen.getByLabelText('API anahtarınız'), 'wrong');
    await user.click(screen.getByRole('button', { name: 'Güvenli giriş yap' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Anahtar geçersiz');
    expect(screen.getByLabelText('API anahtarınız')).toHaveValue('');
  });
});
