// Where the session JWT lives. localStorage so it survives reloads, with an
// in-memory fallback for environments where storage is unavailable (privacy
// mode, SSR). Plain (non-rune) module so `leads-api.ts` can read the header
// without pulling reactive state into its import graph; `auth-store.svelte.ts`
// wraps these for the UI.

const STORAGE_KEY = 'pilot.authToken';

let memToken: string | null = null;

function storage(): Storage | null {
  try {
    if (typeof localStorage === 'undefined') return null;
    // Guard against partial/blocked Storage (privacy mode, some test envs):
    // fall back to the in-memory token rather than throwing on use.
    if (typeof localStorage.getItem !== 'function' || typeof localStorage.setItem !== 'function') {
      return null;
    }
    return localStorage;
  } catch {
    return null; // accessing localStorage can throw (blocked cookies/storage)
  }
}

export function getToken(): string | null {
  const s = storage();
  return s ? s.getItem(STORAGE_KEY) : memToken;
}

export function setToken(token: string): void {
  const s = storage();
  if (s) s.setItem(STORAGE_KEY, token);
  else memToken = token;
}

export function clearToken(): void {
  storage()?.removeItem(STORAGE_KEY);
  memToken = null;
}

/** `{ Authorization: 'Bearer <jwt>' }` when signed in, else `{}`. */
export function authHeader(): Record<string, string> {
  const t = getToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}
