import { describe, it, expect } from 'vitest';
import {
  emptyTaskFilter,
  matchesTask,
  taskQueryString,
  dueBeforeFor,
  activeTaskFilterCount,
  isTaskInDigest,
  type TaskFilter,
} from '../../src/lib/task-filter';
import type { Task } from '../../src/lib/tasks-api';

const TODAY = '2026-06-06';

function task(over: Partial<Task> = {}): Task {
  return {
    id: 1,
    title: 'Call Michael',
    description: 're: tower',
    status: 'open',
    priority: 'none',
    due_date: null,
    assignee_user_id: null,
    lead_cluster_id: null,
    tower_asr: null,
    labels: [],
    source: 'manual',
    created_by_user_id: 1,
    created_at: '',
    updated_at: '',
    completed_at: null,
    ...over,
  };
}

function filter(over: Partial<TaskFilter> = {}): TaskFilter {
  return { ...emptyTaskFilter(), ...over };
}

describe('task-filter (UI overhaul P2 / #110)', () => {
  it('empty filter matches everything and has no query string', () => {
    expect(taskQueryString(emptyTaskFilter(), TODAY)).toBe('');
    expect(matchesTask(task(), emptyTaskFilter(), TODAY)).toBe(true);
    expect(activeTaskFilterCount(emptyTaskFilter())).toBe(0);
  });

  // ── byte-for-byte query string (the canonical API contract) ────────────────
  it('emits a deterministic query string in field order', () => {
    const f = filter({
      status: 'open',
      priority: 'high',
      assignee: 7,
      leadClusterId: 'cidA',
      towerAsr: '000046',
      source: 'manual',
      label: 'Outreach',
      q: 're: tower',
    });
    expect(taskQueryString(f, TODAY)).toBe(
      'status=open&priority=high&assignee=7&lead=cidA&tower=000046&source=manual&label=outreach&q=re%3A+tower',
    );
  });

  it('unassigned overrides assignee in both query + predicate', () => {
    const f = filter({ unassigned: true, assignee: 7 });
    expect(taskQueryString(f, TODAY)).toBe('unassigned=true');
    expect(matchesTask(task({ assignee_user_id: null }), f, TODAY)).toBe(true);
    expect(matchesTask(task({ assignee_user_id: 7 }), f, TODAY)).toBe(false);
  });

  // ── per-field predicate ────────────────────────────────────────────────────
  it('filters by status / priority / links / source / label', () => {
    expect(matchesTask(task({ status: 'done' }), filter({ status: 'done' }), TODAY)).toBe(true);
    expect(matchesTask(task({ status: 'open' }), filter({ status: 'done' }), TODAY)).toBe(false);
    expect(matchesTask(task({ priority: 'high' }), filter({ priority: 'high' }), TODAY)).toBe(true);
    expect(
      matchesTask(task({ lead_cluster_id: 'cidA' }), filter({ leadClusterId: 'cidA' }), TODAY),
    ).toBe(true);
    expect(matchesTask(task({ tower_asr: '46' }), filter({ towerAsr: '46' }), TODAY)).toBe(true);
    expect(matchesTask(task({ source: 'auto' }), filter({ source: 'auto' }), TODAY)).toBe(true);
    expect(matchesTask(task({ labels: ['dev'] }), filter({ label: 'DEV' }), TODAY)).toBe(true);
    expect(matchesTask(task({ labels: ['ops'] }), filter({ label: 'dev' }), TODAY)).toBe(false);
  });

  it('free-text search matches title and description (case-insensitive)', () => {
    expect(matchesTask(task(), filter({ q: 'michael' }), TODAY)).toBe(true); // title
    expect(matchesTask(task(), filter({ q: 'TOWER' }), TODAY)).toBe(true); // description
    expect(matchesTask(task(), filter({ q: 'zzz' }), TODAY)).toBe(false);
  });

  // ── due window ──────────────────────────────────────────────────────────────
  it('maps due windows to a due_before bound relative to today', () => {
    expect(dueBeforeFor('overdue', TODAY)).toBe('2026-06-05');
    expect(dueBeforeFor('today', TODAY)).toBe('2026-06-06');
    expect(dueBeforeFor('week', TODAY)).toBe('2026-06-13');
    expect(dueBeforeFor('', TODAY)).toBeNull();
  });

  it('overdue keeps only tasks due before today', () => {
    const f = filter({ dueWindow: 'overdue' });
    expect(matchesTask(task({ due_date: '2026-06-01' }), f, TODAY)).toBe(true);
    expect(matchesTask(task({ due_date: '2026-06-06' }), f, TODAY)).toBe(false);
    expect(matchesTask(task({ due_date: null }), f, TODAY)).toBe(false);
    expect(taskQueryString(f, TODAY)).toBe('due_before=2026-06-05');
  });

  // ── Dashboard Tasks digest rule (#111) ──────────────────────────────────────
  it('digest = due today/tomorrow OR high-priority, never done', () => {
    expect(isTaskInDigest(task({ due_date: TODAY }), TODAY)).toBe(true);
    expect(isTaskInDigest(task({ due_date: '2026-06-07' }), TODAY)).toBe(true); // tomorrow
    expect(isTaskInDigest(task({ due_date: '2026-06-09' }), TODAY)).toBe(false); // later
    expect(isTaskInDigest(task({ priority: 'high', due_date: null }), TODAY)).toBe(true);
    expect(isTaskInDigest(task({ priority: 'high', status: 'done' }), TODAY)).toBe(false);
    expect(isTaskInDigest(task({ due_date: null }), TODAY)).toBe(false);
  });

  it('combines filters with AND', () => {
    const f = filter({ status: 'open', priority: 'high', q: 'michael' });
    expect(matchesTask(task({ status: 'open', priority: 'high' }), f, TODAY)).toBe(true);
    expect(matchesTask(task({ status: 'done', priority: 'high' }), f, TODAY)).toBe(false);
    expect(activeTaskFilterCount(f)).toBe(3);
  });
});
