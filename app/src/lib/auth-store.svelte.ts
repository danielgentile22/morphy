// Reactive sign-in state for the username/password flow (Slice 1 / #76).
// Wraps the plain `auth-token.ts` storage and the `leads-api` auth endpoints.
// Mirrors the singleton-class + $state pattern of leads-store.svelte.ts.
//
// The app-load gate (#85) keys on `verified` — a session is only trusted
// after the persisted token has been validated against /api/auth/me, so a
// stale token can never mount the app or trigger a data fetch.

import { login as apiLogin, fetchMe, ApiError } from './leads-api';
import { clearToken, getToken, setToken } from './auth-token';

class AuthStore {
  token = $state<string | null>(getToken());
  email = $state<string | null>(null);
  // The signed-in user's team name (#86) — shown next to the username so
  // it's always clear which identity and board you're working in.
  team = $state<string | null>(null);
  // True while a persisted token is being validated at app load — the gate
  // shows a "checking session" state instead of flashing the sign-in form
  // at users who are already signed in.
  restoring = $state<boolean>(getToken() !== null);

  get signedIn(): boolean {
    return this.token !== null;
  }

  /** A *verified* session: the token has been accepted by /api/auth/me.
   *  The app (map, nav, panels, data fetches) mounts only behind this. */
  get verified(): boolean {
    return this.token !== null && this.email !== null;
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
    if (!this.token) {
      this.restoring = false;
      return;
    }
    try {
      const me = await fetchMe();
      this.email = me.email;
      this.team = me.team ?? null;
    } catch (e) {
      // A stale/expired token surfaces as 401 — drop it so the UI shows sign-in.
      if (e instanceof ApiError && e.status === 401) this.signOut();
      // Any other failure (backend unreachable) leaves the session unverified:
      // the gate stays up and the sign-in form surfaces the connection error.
    } finally {
      this.restoring = false;
    }
  }

  signOut(): void {
    clearToken();
    this.token = null;
    this.email = null;
    this.team = null;
  }
}

export const auth = new AuthStore();
