import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';
import { CsvPreview } from '../components/CsvPreview';

describe('CSV preview', () => {
  it('renders hostile HTML as text and announces row truncation', async () => {
    HTMLDialogElement.prototype.showModal = function () {
      this.setAttribute('open', '');
    };
    HTMLDialogElement.prototype.close = function () {
      this.removeAttribute('open');
    };
    const html = '<img src=x onerror=alert(1)>';
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          name: 'x.csv',
          headers: ['value'],
          rows: [[html]],
          truncated: true,
          row_limit: 200,
          size: 30,
        }),
      ),
    );
    render(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <CsvPreview
          file={{ name: 'x.csv', path: '2026/x.csv', size: 30, is_csv: true, modified_at: '' }}
          customerId="amy"
          onClose={vi.fn()}
        />
      </QueryClientProvider>,
    );
    expect(await screen.findByText(html)).toBeInTheDocument();
    expect(document.querySelector('img')).toBeNull();
    expect(screen.getByText(/İlk 200 satır/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Dosyayı indir' })).toHaveAttribute(
      'href',
      '/api/files/download?path=2026%2Fx.csv',
    );
  });
});
