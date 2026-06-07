/**
 * Task filter model (UI overhaul P2 / #110).
 *
 * Mirrors the owner FilterModel pattern: ONE field registry projects two ways
 * so they can't drift —
 *   - `taskQueryString(f, today)` → the API query string (the canonical query
 *     contract; unit-tested byte-for-byte, like `composeOwnerWhere`).
 *   - `matchesTask(task, f, today)` → the runtime predicate.
 * Both fall out of `TASK_FILTER_FIELDS`, so filter-by-any-field + the free-text
 * search are one source of truth across the API and the client.
 *
 * `today` (an ISO date) is injected so the due-window field stays pure +
 * deterministic. The backend (`TaskStore.list_filtered`) implements the same
 * semantics server-side.
 */

import type { Task } from './tasks-api';

export type DueWindow = '' | 'overdue' | 'today' | 'week';

export interface TaskFilter {
  status: '' | 'open' | 'in_progress' | 'done';
  priority: '' | 'none' | 'low' | 'med' | 'high';
  /** assignee user id, or null for "any"; `unassigned` overrides it. */
  assignee: number | null;
  unassigned: boolean;
  leadClusterId: string;
  towerAsr: string;
  source: '' | 'manual' | 'auto';
  label: string;
  dueWindow: DueWindow;
  /** free-text — matches title/description (contains, case-insensitive). */
  q: string;
}

export function emptyTaskFilter(): TaskFilter {
  return {
    status: '',
    priority: '',
    assignee: null,
    unassigned: false,
    leadClusterId: '',
    towerAsr: '',
    source: '',
    label: '',
    dueWindow: '',
    q: '',
  };
}

/** Add `days` to an ISO date, returning ISO. Pure (no Date.now). */
function addDays(iso: string, days: number): string {
  const d = new Date(iso + 'T00:00:00Z');
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

/** The `due_before` bound for a window, relative to `today` (ISO), or null. */
export function dueBeforeFor(window: DueWindow, today: string): string | null {
  switch (window) {
    case 'overdue':
      return addDays(today, -1); // strictly before today
    case 'today':
      return today; // due today or earlier
    case 'week':
      return addDays(today, 7);
    default:
      return null;
  }
}

interface TaskField {
  isActive: (f: TaskFilter) => boolean;
  /** `[key, value]` API query param, or null when inactive. */
  toParam: (f: TaskFilter, today: string) => [string, string] | null;
  test: (t: Task, f: TaskFilter, today: string) => boolean;
}

function contains(hay: string, needle: string): boolean {
  return hay.toLowerCase().includes(needle.trim().toLowerCase());
}

/**
 * The whole task-filter vocabulary, in query-string emission order (stable so
 * `taskQueryString` is deterministic — the unit tests assert exact strings).
 */
export const TASK_FILTER_FIELDS: readonly TaskField[] = [
  {
    isActive: (f) => f.status !== '',
    toParam: (f) => ['status', f.status],
    test: (t, f) => t.status === f.status,
  },
  {
    isActive: (f) => f.priority !== '',
    toParam: (f) => ['priority', f.priority],
    test: (t, f) => t.priority === f.priority,
  },
  {
    isActive: (f) => f.unassigned,
    toParam: () => ['unassigned', 'true'],
    test: (t) => t.assignee_user_id == null,
  },
  {
    // Suppressed when `unassigned` is set (mutually exclusive).
    isActive: (f) => !f.unassigned && f.assignee != null,
    toParam: (f) => ['assignee', String(f.assignee)],
    test: (t, f) => t.assignee_user_id === f.assignee,
  },
  {
    isActive: (f) => f.leadClusterId !== '',
    toParam: (f) => ['lead', f.leadClusterId],
    test: (t, f) => t.lead_cluster_id === f.leadClusterId,
  },
  {
    isActive: (f) => f.towerAsr !== '',
    toParam: (f) => ['tower', f.towerAsr],
    test: (t, f) => t.tower_asr === f.towerAsr,
  },
  {
    isActive: (f) => f.source !== '',
    toParam: (f) => ['source', f.source],
    test: (t, f) => t.source === f.source,
  },
  {
    isActive: (f) => f.label.trim() !== '',
    toParam: (f) => ['label', f.label.trim().toLowerCase()],
    test: (t, f) => t.labels.includes(f.label.trim().toLowerCase()),
  },
  {
    isActive: (f) => f.dueWindow !== '',
    toParam: (f, today) => {
      const b = dueBeforeFor(f.dueWindow, today);
      return b ? ['due_before', b] : null;
    },
    test: (t, f, today) => {
      const b = dueBeforeFor(f.dueWindow, today);
      return b !== null && t.due_date != null && t.due_date <= b;
    },
  },
  {
    isActive: (f) => f.q.trim() !== '',
    toParam: (f) => ['q', f.q.trim()],
    test: (t, f) => contains(t.title, f.q) || contains(t.description, f.q),
  },
];

/** The canonical API query string for a filter — '' when nothing is active.
 *  Params are emitted in TASK_FILTER_FIELDS order (deterministic). */
export function taskQueryString(f: TaskFilter, today: string): string {
  const params = new URLSearchParams();
  for (const field of TASK_FILTER_FIELDS) {
    if (!field.isActive(f)) continue;
    const p = field.toParam(f, today);
    if (p) params.set(p[0], p[1]);
  }
  return params.toString();
}

/** True when this task passes every active filter. Empty filter ⇒ all tasks. */
export function matchesTask(t: Task, f: TaskFilter, today: string): boolean {
  for (const field of TASK_FILTER_FIELDS) {
    if (field.isActive(f) && !field.test(t, f, today)) return false;
  }
  return true;
}

/** How many filter controls are currently constraining the result. */
export function activeTaskFilterCount(f: TaskFilter): number {
  return TASK_FILTER_FIELDS.reduce((n, field) => n + (field.isActive(f) ? 1 : 0), 0);
}

/** The Dashboard Tasks digest rule (#111, D9): not done, AND either due
 *  today/tomorrow OR high-priority (regardless of date). `today` injected
 *  (ISO) for purity. */
export function isTaskInDigest(t: Task, today: string): boolean {
  if (t.status === 'done') return false;
  if (t.priority === 'high') return true;
  if (t.due_date == null) return false;
  const tomorrow = addDays(today, 1);
  return t.due_date === today || t.due_date === tomorrow;
}
