// Reactive sign-in state for the username/password flow (Slice 1 / #76).
// Wraps the plain `auth-token.ts` storage and the `leads-api` auth endpoints.
// Mirrors the singleton-class + $state pattern of leads-store.svelte.ts.

import { login as apiLogin, fetchMe, ApiError } from './leads-api';
import { clearToken, getToken, setToken } from './auth-token';

class AuthStore {
  token = $state<string | null>(getToken());
  email = $state<string | null>(null);

  get signedIn(): boolean {
    return this.token !== null;
  }

  /** Verify username/password, persist the session JWT, and load the
   *  signed-in identity. Throws (with the backend's specific message) on a
   *  failed login so the sign-in form can surface it. */
  async login(username: string, password: string): Promise<void> {
    const { access_token } = await apiLogin(username.trim(), password);
    setToken(access_token);
    this.token = access_token;
    await this.loadMe();
  }

  /** Validate a persisted token on boot + populate the signed-in username. */
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
  }
}

export const auth = new AuthStore();
