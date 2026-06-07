// Runes store for the Lead surfaces (Candidates + Lead page). Mirrors the
// pattern of stores.svelte.ts (a singleton class with $state fields).

import {
  ApiError,
  appendAttempt,
  fetchCandidates,
  fetchCounts,
  fetchLead,
  fetchMyLeads,
  mergeCluster,
  pursueOwner,
  splitCluster,
  updateLead,
  type AttemptPayload,
  type ContactFields,
  type LeadDetail,
  type OwnerSummary,
} from './leads-api';
import { auth } from './auth-store.svelte';
import { canTransition, type LeadStatus } from './lead-status';

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

  // My-Leads kanban worklist (Slice 5 / #51): owners advanced off New.
  myLeads = $state<OwnerSummary[]>([]);
  myLeadsCount = $state(0);
  myLeadsStatus = $state<Loadable>('idle');
  myLeadsError = $state<string | null>(null);

  // Live nav counts — loaded once a session is signed in and refreshed on
  // every status change, so both badges stay current on any surface.
  countsStatus = $state<Loadable>('idle');

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

  async loadMyLeads(): Promise<void> {
    this.myLeadsStatus = 'loading';
    this.myLeadsError = null;
    try {
      const res = await fetchMyLeads();
      this.myLeads = res.leads;
      this.myLeadsCount = res.count;
      this.myLeadsStatus = 'ready';
    } catch (e) {
      this.myLeadsError = handle(e);
      this.myLeadsStatus = 'error';
    }
  }

  /** Refresh both nav counts. Best-effort: a failure leaves the last known
   *  counts in place (the badges are informational). */
  async loadCounts(): Promise<void> {
    this.countsStatus = 'loading';
    try {
      const res = await fetchCounts();
      this.candidatesCount = res.candidates;
      this.myLeadsCount = res.my_leads;
      this.countsStatus = 'ready';
    } catch (e) {
      handle(e); // still signs out on a 401
      this.countsStatus = 'error';
    }
  }

  /** Drag a card to a new lane: change its status and persist. Optimistically
   *  moves the card, then reverts it if the server rejects the transition
   *  (the server is authoritative). The client-side ladder check gives
   *  immediate feedback for an illegal drop without a round-trip. Returns
   *  true if the move persisted. */
  async moveLead(displayClusterId: string, to: LeadStatus): Promise<boolean> {
    const i = this.myLeads.findIndex((o) => o.display_cluster_id === displayClusterId);
    if (i === -1) return false;
    const from = this.myLeads[i].status;
    if (from === to) return true;
    if (!canTransition(from, to)) {
      this.myLeadsError = `Illegal move: ${from} → ${to}`;
      return false;
    }
    this.myLeadsError = null;
    this.myLeads[i].status = to; // optimistic — the card jumps lanes now
    try {
      await updateLead(displayClusterId, { status: to });
      void this.loadCounts();
      return true;
    } catch (e) {
      this.myLeads[i].status = from; // server said no → snap back
      this.myLeadsError = handle(e);
      return false;
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
      // A status change moves the owner between Candidates and My-Leads —
      // refresh the nav counts so both badges stay live.
      if (patch.status !== undefined) void this.loadCounts();
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

  /** Pursue an owner from Explore (#109): advance New → Researching + record
   *  the trigger antenna. Refreshes the in-memory lead + nav counts (the owner
   *  moved from the discovery pool into Leads). Returns true on success. */
  async pursue(displayClusterId: string, triggerAsr: string): Promise<boolean> {
    this.saving = true;
    this.saveError = null;
    try {
      this.lead = await pursueOwner(displayClusterId, triggerAsr);
      void this.loadCounts();
      return true;
    } catch (e) {
      this.saveError = handle(e);
      return false;
    } finally {
      this.saving = false;
    }
  }

  /** Merge another owner-cluster into this Lead, or split a merged-in one back
   *  out (Slice 7 / #53). Both refresh the in-memory lead (now the merged/split
   *  result) and the nav counts, since the effective owner population changed. */
  async mergeOwner(displayClusterId: string, sourceClusterId: string): Promise<boolean> {
    return this.#override(() => mergeCluster(displayClusterId, sourceClusterId));
  }

  async splitOwner(displayClusterId: string, sourceClusterId: string): Promise<boolean> {
    return this.#override(() => splitCluster(displayClusterId, sourceClusterId));
  }

  async #override(call: () => Promise<LeadDetail>): Promise<boolean> {
    this.saving = true;
    this.saveError = null;
    try {
      this.lead = await call();
      void this.loadCounts(); // merge/split changes the Candidates / My-Leads totals
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
