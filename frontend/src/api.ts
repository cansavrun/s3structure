export type Customer = { id: string; name: string };
export type Me = {
  customer: Customer;
  key_name: string;
  expires_at: string;
  preview_max_bytes: number;
};
export type Folder = { name: string; path: string };
export type FileEntry = {
  name: string;
  path: string;
  size: number;
  modified_at: string;
  is_csv: boolean;
};
export type FilePage = {
  path: string;
  folders: Folder[];
  files: FileEntry[];
  next_cursor: string | null;
};
export type Preview = {
  name: string;
  headers: string[];
  rows: string[][];
  truncated: boolean;
  row_limit: number;
  size: number;
};

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public requestId?: string,
  ) {
    super(message);
  }
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...options,
    credentials: 'same-origin',
    cache: 'no-store',
    headers: {
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...options.headers,
    },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    if (response.status === 401 && path !== '/auth/login' && path !== '/me') {
      window.dispatchEvent(new Event('tenantfiles:unauthorized'));
    }
    throw new ApiError(
      response.status,
      typeof body.detail === 'string' ? body.detail : 'İstek tamamlanamadı',
      response.headers.get('X-Request-ID') ?? undefined,
    );
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const downloadUrl = (path: string) => `/api/files/download?${new URLSearchParams({ path })}`;
export const formatBytes = (bytes: number) =>
  bytes < 1024
    ? `${bytes} B`
    : bytes < 1024 ** 2
      ? `${(bytes / 1024).toFixed(1)} KB`
      : `${(bytes / 1024 ** 2).toFixed(1)} MB`;

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Bağlantı kurulamadı. Lütfen yeniden deneyin.';
}
