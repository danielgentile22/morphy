// Runes store for the Lead surfaces (Candidates + Lead page). Mirrors the
// pattern of stores.svelte.ts (a singleton class with $state fields).

import {
  ApiError,
  appendAttempt,
  fetchCandidates,
  fetchLead,
  updateLead,
  type AttemptPayload,
  type ContactFields,
  type LeadDetail,
  type OwnerSummary,
} from './leads-api';
import { auth } from './auth-store.svelte';
import type { LeadStatus } from './lead-status';

type Loadable = 'idle' | 'loading' | 'ready' | 'error';

/** Sign out on a 401 so the UI falls back to the sign-in surface, and
 *  return the message to display for any error. */
function handle(e: unknown): string {
  if (e instanceof ApiError && e.status === 401) auth.signOut();
  return e instanceof Error ? e.message : String(e);
}

class LeadsStore {
  candidates = $state<OwnerSummary[]>([]);
  candidatesCount = $state(0);
  candidatesStatus = $state<Loadable>('idle');
  candidatesError = $state<string | null>(null);

  lead = $state<LeadDetail | null>(null);
  leadStatus = $state<Loadable>('idle');
  leadError = $state<string | null>(null);
  saving = $state(false);
  saveError = $state<string | null>(null);

  async loadCandidates(): Promise<void> {
    this.candidatesStatus = 'loading';
    this.candidatesError = null;
    try {
      const res = await fetchCandidates();
      this.candidates = res.candidates;
      this.candidatesCount = res.count;
      this.candidatesStatus = 'ready';
    } catch (e) {
      this.candidatesError = handle(e);
      this.candidatesStatus = 'error';
    }
  }

  async loadLead(displayClusterId: string): Promise<void> {
    this.leadStatus = 'loading';
    this.leadError = null;
    this.lead = null;
    this.saveError = null;
    try {
      this.lead = await fetchLead(displayClusterId);
      this.leadStatus = 'ready';
    } catch (e) {
      this.leadError = handle(e);
      this.leadStatus = 'error';
    }
  }

  /** Persist status, notes, and/or contact fields; refreshes the in-memory
   *  lead on success. Returns true on success, false if the API rejected it. */
  async saveLead(
    displayClusterId: string,
    patch: { status?: LeadStatus; notes?: string } & Partial<ContactFields>,
  ): Promise<boolean> {
    this.saving = true;
    this.saveError = null;
    try {
      this.lead = await updateLead(displayClusterId, patch);
      return true;
    } catch (e) {
      // A 409 means an illegal ladder move; a 401 signs out (see handle()).
      this.saveError = handle(e);
      return false;
    } finally {
      this.saving = false;
    }
  }

  /** Log a manual contact attempt; refreshes the lead (the new row appears
   *  in the activity stream alongside any auto-logged status rows). */
  async addAttempt(displayClusterId: string, payload: AttemptPayload): Promise<boolean> {
    this.saving = true;
    this.saveError = null;
    try {
      this.lead = await appendAttempt(displayClusterId, payload);
      return true;
    } catch (e) {
      this.saveError = handle(e);
      return false;
    } finally {
      this.saving = false;
    }
  }
}

export const leads = new LeadsStore();
