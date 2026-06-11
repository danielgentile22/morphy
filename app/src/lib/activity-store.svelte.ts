// Runes store for the Dashboard activity views (UI overhaul P3 / #112) — the
// ONE read model History (chronological) and Calendar (time-grid) both render.
// Filters (lead/member/channel/date) project to the shared /api/activity query.

import { request, ApiError } from './leads-api';
import { auth } from './auth-store.svelte';

export interface ActivityEvent {
  id: number; // ContactAttempt PK — stable key for keyed {#each}
  date: string;
  kind: 'touch' | 'reply' | 'status' | 'flag';
  channel: string;
  cluster_id: string;
  owner_name: string;
  logged_by_user_id: number | null;
  member_name: string;
  summary: string;
}

export interface ActivityFilter {
  lead: string;
  member: number | null;
  channel: string;
  dateFrom: string;
  dateTo: string;
}

export function emptyActivityFilter(): ActivityFilter {
  return { lead: '', member: null, channel: '', dateFrom: '', dateTo: '' };
}

function queryString(f: ActivityFilter): string {
  const p = new URLSearchParams();
  if (f.lead) p.set('lead', f.lead);
  if (f.member != null) p.set('member', String(f.member));
  if (f.channel) p.set('channel', f.channel);
  if (f.dateFrom) p.set('date_from', f.dateFrom);
  if (f.dateTo) p.set('date_to', f.dateTo);
  return p.toString();
}

interface ActivityResponse {
  count: number;
  events: ActivityEvent[];
  last_contact_on: string | null;
  last_reply_on: string | null;
}

export class ActivityStore {
  events = $state<ActivityEvent[]>([]);
  status = $state<'idle' | 'loading' | 'ready' | 'error'>('idle');
  lastContactOn = $state<string | null>(null);
  lastReplyOn = $state<string | null>(null);
  // The union of channels ever seen — drives the channel-filter options so they
  // stay stable instead of collapsing to just the selected channel after a pick
  // (the unfiltered mount load seeds the full vocabulary). Never shrinks.
  channelVocab = $state<string[]>([]);

  filter = $state<ActivityFilter>(emptyActivityFilter());

  // Coalesce concurrent in-flight loads into one request (PRD #125 / #127):
  // stacking History + Calendar on one Dashboard makes both call load() on
  // mount, which would otherwise fire two identical /activity fetches. Only
  // *concurrent* loads share this promise — it clears on settle, so a later
  // load (Dashboard re-open, a filter change) still refetches fresh data.
  private loading: Promise<void> | null = null;

  load(): Promise<void> {
    return (this.loading ??= this.runLoad().finally(() => {
      this.loading = null;
    }));
  }

  private async runLoad(): Promise<void> {
    this.status = 'loading';
    try {
      const qs = queryString(this.filter);
      const res = await request<ActivityResponse>(`/activity${qs ? `?${qs}` : ''}`);
      this.events = res.events;
      this.lastContactOn = res.last_contact_on;
      this.lastReplyOn = res.last_reply_on;
      const vocab = new Set(this.channelVocab);
      for (const e of res.events) vocab.add(e.channel);
      this.channelVocab = [...vocab].sort();
      this.status = 'ready';
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) auth.signOut();
      this.status = 'error';
    }
  }

  setFilter(patch: Partial<ActivityFilter>): void {
    this.filter = { ...this.filter, ...patch };
    void this.load();
  }
  resetFilter(): void {
    this.filter = emptyActivityFilter();
    void this.load();
  }
}

export const activity = new ActivityStore();
