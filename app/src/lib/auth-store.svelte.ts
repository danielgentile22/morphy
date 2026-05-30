// Reactive sign-in state for the magic-link flow (Slice 2 / #48). Wraps the
// plain `auth-token.ts` storage and the `leads-api` auth endpoints. Mirrors
// the singleton-class + $state pattern of leads-store.svelte.ts.

import { exchangeToken, fetchMe, requestLink, ApiError } from './leads-api';
import { clearToken, getToken, setToken } from './auth-token';

type Phase = 'idle' | 'requesting' | 'link-sent' | 'exchanging' | 'error';

function message(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

class AuthStore {
  token = $state<string | null>(getToken());
  email = $state<string | null>(null);
  // In dev the backend echoes the token so we can prefill the exchange field.
  devToken = $state<string | null>(null);
  phase = $state<Phase>('idle');
  error = $state<string | null>(null);

  get signedIn(): boolean {
    return this.token !== null;
  }

  /** Step 1: ask the backend to email a magic link. Always "succeeds" server
   *  side (no email enumeration); in dev we capture the returned token. */
  async requestLink(email: string): Promise<void> {
    this.phase = 'requesting';
    this.error = null;
    this.devToken = null;
    try {
      const res = await requestLink(email.trim());
      this.devToken = res.dev_token;
      this.phase = 'link-sent';
    } catch (e) {
      this.error = message(e);
      this.phase = 'error';
    }
  }

  /** Step 2: exchange the token for a session JWT and persist it. */
  async exchange(token: string): Promise<boolean> {
    this.phase = 'exchanging';
    this.error = null;
    try {
      const res = await exchangeToken(token.trim());
      setToken(res.access_token);
      this.token = res.access_token;
      this.phase = 'idle';
      void this.loadMe();
      return true;
    } catch (e) {
      this.error = message(e);
      this.phase = 'error';
      return false;
    }
  }

  /** Validate a persisted token on boot + populate the signed-in email. */
  async loadMe(): Promise<void> {
    if (!this.token) return;
    try {
      this.email = (await fetchMe()).email;
    } catch (e) {
      // A stale/expired token surfaces as 401 — drop it so the UI shows sign-in.
      if (e instanceof ApiError && e.status === 401) this.signOut();
    }
  }

  signOut(): void {
    clearToken();
    this.token = null;
    this.email = null;
    this.devToken = null;
    this.phase = 'idle';
    this.error = null;
  }
}

export const auth = new AuthStore();
