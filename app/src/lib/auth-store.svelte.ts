// Reactive sign-in state for the username/password flow (Slice 1 / #76).
// Mirrors the singleton-class + $state pattern of leads-store.svelte.ts.
//
// The session JWT lives in an httpOnly cookie the backend sets at login
// (PRD #130) — page scripts can never read it, so there is no token state
// here at all. Identity comes from /api/auth/me, which the cookie
// authenticates; the app-load gate (#85) keys on `verified` — the app mounts
// only after the me-endpoint has accepted the session.

import { login as apiLogin, logout as apiLogout, fetchMe, ApiError } from './leads-api';

class AuthStore {
  email = $state<string | null>(null);
  // The signed-in user's team name (#86) — shown next to the username so
  // it's always clear which identity and board you're working in.
  team = $state<string | null>(null);
  // The friendly display name set in Settings (PRD #121); '' / null falls back
  // to the email everywhere it's shown.
  displayName = $state<string | null>(null);
  // True while the session cookie is being validated at app load — the gate
  // shows a "checking session" state instead of flashing the sign-in form
  // at users who are already signed in.
  restoring = $state<boolean>(true);

  /** A *verified* session: the cookie has been accepted by /api/auth/me.
   *  The app (map, nav, panels, data fetches) mounts only behind this. */
  get verified(): boolean {
    return this.email !== null;
  }

  /** Verify username/password (the backend sets the session cookie) and load
   *  the signed-in identity. Throws (with the backend's specific message) on a
   *  failed login so the sign-in form can surface it. */
  async login(username: string, password: string): Promise<void> {
    await apiLogin(username.trim(), password);
    await this.loadMe();
  }

  /** Validate the session cookie on boot + populate the signed-in username. */
  async loadMe(): Promise<void> {
    try {
      const me = await fetchMe();
      this.email = me.email;
      this.team = me.team ?? null;
      this.displayName = me.display_name ?? null;
    } catch (e) {
      // No session (or a stale one) surfaces as 401 — the gate shows sign-in.
      if (e instanceof ApiError && e.status === 401) this.clear();
      // Any other failure (backend unreachable) leaves the session unverified:
      // the gate stays up and the sign-in form surfaces the connection error.
    } finally {
      this.restoring = false;
    }
  }

  /** Sign out: clear local state immediately, and have the backend expire the
   *  session cookie — which also ends this browser's access to the gated
   *  /data files (PRD #130). Fire-and-forget on the network leg. */
  signOut(): void {
    this.clear();
    void apiLogout().catch(() => {
      // Best-effort: an unreachable backend still leaves the UI signed out;
      // the cookie dies at its TTL.
    });
  }

  private clear(): void {
    this.email = null;
    this.team = null;
    this.displayName = null;
  }

  /** The name to show for the signed-in user — their display name, or the email
   *  when unset. */
  get name(): string {
    return this.displayName?.trim() || this.email || '';
  }
}

export const auth = new AuthStore();
