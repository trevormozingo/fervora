import { getIdToken } from '@/services/auth';
import { config } from '@/config';

/** Thrown when the device cannot reach the backend at all. */
export class NetworkError extends Error {
  constructor(message = 'Unable to connect to the server') {
    super(message);
    this.name = 'NetworkError';
  }
}

/** Authenticated fetch wrapper — adds auth header and throws on non-ok responses. */
export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getIdToken();
  const headers: Record<string, string> = {
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(init?.headers as Record<string, string> ?? {}),
  };
  let res: Response;
  try {
    res = await fetch(`${config.apiBaseUrl}${path}`, { ...init, headers });
  } catch {
    throw new NetworkError();
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `Request failed (${res.status})`);
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return res.json();
}
