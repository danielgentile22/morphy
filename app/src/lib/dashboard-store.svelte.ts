// Runes store for the Dashboard (UI overhaul P2 / #111). Owns the Attention
// feed — unhandled replies + overdue tasks — whose count is the nav badge.
// Loaded once a session is signed in (like the lead counts).

import { request, ApiError } from './leads-api';
import { auth } from './auth-store.svelte';

export interface AttentionItem {
  kind: 'reply' | 'overdue_task';
  title: string;
  when: string;
  cluster_id: string;
  owner_name: string;
  task_id: number | null;
}

interface AttentionResponse {
  count: number;
  items: AttentionItem[];
}

function fetchAttention(): Promise<AttentionResponse> {
  return request<AttentionResponse>('/attention');
}

function dismissReply(clusterId: string): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>('/attention/dismiss', {
    method: 'POST',
    body: JSON.stringify({ cluster_id: clusterId }),
  });
}

class DashboardStore {
  items = $state<AttentionItem[]>([]);
  count = $state(0);
  status = $state<'idle' | 'loading' | 'ready' | 'error'>('idle');

  async loadAttention(): Promise<void> {
    this.status = 'loading';
    try {
      const res = await fetchAttention();
      this.items = res.items;
      this.count = res.count;
      this.status = 'ready';
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) auth.signOut();
      this.status = 'error';
    }
  }

  /** Dismiss a reply (appends a clearing activity row), then refresh. */
  async dismiss(clusterId: string): Promise<void> {
    try {
      await dismissReply(clusterId);
      await this.loadAttention();
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) auth.signOut();
    }
  }
}

export const dashboard = new DashboardStore();
