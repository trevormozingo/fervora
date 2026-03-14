import { getIdToken } from '@/services/auth';
import { config } from '@/config';

/** Authenticated fetch wrapper — adds auth header and throws on non-ok responses. */
export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getIdToken();
  const headers: Record<string, string> = {
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(init?.headers as Record<string, string> ?? {}),
  };
  const res = await fetch(`${config.apiBaseUrl}${path}`, { ...init, headers });
  if (!res.ok) throw new Error(`${res.status}`);
  if (res.status === 204) {
    return undefined as T;
  }
  return res.json();
}
