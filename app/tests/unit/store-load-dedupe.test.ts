import { describe, it, expect, vi, afterEach } from 'vitest';
import { ActivityStore } from '../../src/lib/activity-store.svelte';
import { TasksStore } from '../../src/lib/tasks-store.svelte';

// The store load-dedupe guard (PRD #125 / #127). Stacking History + Calendar
// (and Tasks/Stats) on one scrolling Dashboard means several views call the
// same loader on mount; the guard collapses those *concurrent* loads into one
// underlying request without caching completed loads. We assert on observable
// behavior only — the count of underlying requests + the resulting store state
// — by stubbing the lowest layer (`fetch`, what `request` calls) and counting
// invocations, mirroring leads-api.test.ts. Never reach into the private guard.

interface PendingCall {
  url: string;
  resolve: (body: unknown) => void;
  fail: (status: number, detail?: string) => void;
}

/** A `fetch` stub that hands back a controllable promise per call, so a test
 *  can keep a request in flight, then settle it ok or with an HTTP error. */
function deferredFetch() {
  const calls: PendingCall[] = [];
  const spy = vi.fn(
    (url: string) =>
      new Promise<Response>((res) => {
        calls.push({
          url,
          resolve: (body) =>
            res({ ok: true, status: 200, json: async () => body } as unknown as Response),
          fail: (status, detail) =>
            res({
              ok: false,
              status,
              statusText: 'Error',
              json: async () => ({ detail }),
            } as unknown as Response),
        });
      }),
  );
  return { spy, calls };
}

const ACTIVITY_OK = {
  count: 1,
  events: [
    {
      id: 1,
      date: '2026-06-01',
      kind: 'touch',
      channel: 'call',
      cluster_id: 'c1',
      owner_name: 'Owner',
      logged_by_user_id: null,
      member_name: '',
      summary: '',
    },
  ],
  last_contact_on: '2026-06-01',
  last_reply_on: null,
};

const TASKS_OK = {
  count: 1,
  tasks: [
    {
      id: 1,
      title: 'T',
      description: '',
      status: 'open',
      priority: 'none',
      due_date: null,
      assignee_user_id: null,
      lead_cluster_id: null,
      tower_asr: null,
      labels: [],
      source: 'manual',
      created_by_user_id: null,
      created_at: '',
      updated_at: '',
      completed_at: null,
    },
  ],
};

const USERS_OK = { count: 1, users: [{ id: 1, email: 'a@b.c', display_name: 'A', name: 'A' }] };

afterEach(() => vi.unstubAllGlobals());

describe('activity store load coalescing (#127)', () => {
  it('collapses concurrent load() calls into exactly one request', async () => {
    const { spy, calls } = deferredFetch();
    vi.stubGlobal('fetch', spy);
    const store = new ActivityStore();

    const p1 = store.load();
    const p2 = store.load();
    const p3 = store.load();
    // All three callers share one in-flight fetch.
    expect(spy).toHaveBeenCalledTimes(1);
    expect(store.status).toBe('loading');

    calls[0].resolve(ACTIVITY_OK);
    await Promise.all([p1, p2, p3]);

    expect(spy).toHaveBeenCalledTimes(1);
    expect(store.status).toBe('ready');
    expect(store.events).toHaveLength(1);
  });

  it('issues a NEW request once the prior load settles (no caching)', async () => {
    const { spy, calls } = deferredFetch();
    vi.stubGlobal('fetch', spy);
    const store = new ActivityStore();

    const p1 = store.load();
    calls[0].resolve(ACTIVITY_OK);
    await p1;
    expect(spy).toHaveBeenCalledTimes(1);

    // A re-open after settle refetches rather than serving stale data.
    const p2 = store.load();
    expect(spy).toHaveBeenCalledTimes(2);
    calls[1].resolve({ ...ACTIVITY_OK, events: [] });
    await p2;
    expect(store.status).toBe('ready');
    expect(store.events).toHaveLength(0);
  });

  it('clears the guard after a failed load so a later load retries', async () => {
    const { spy, calls } = deferredFetch();
    vi.stubGlobal('fetch', spy);
    const store = new ActivityStore();

    const p1 = store.load();
    calls[0].fail(500, 'boom');
    await p1;
    expect(store.status).toBe('error');
    expect(spy).toHaveBeenCalledTimes(1);

    const p2 = store.load();
    expect(spy).toHaveBeenCalledTimes(2);
    calls[1].resolve(ACTIVITY_OK);
    await p2;
    expect(store.status).toBe('ready');
  });
});

describe('tasks store load coalescing (#127)', () => {
  it('collapses concurrent load() calls into exactly one request', async () => {
    const { spy, calls } = deferredFetch();
    vi.stubGlobal('fetch', spy);
    const store = new TasksStore();

    const p1 = store.load();
    const p2 = store.load();
    expect(spy).toHaveBeenCalledTimes(1);
    expect(store.status).toBe('loading');

    calls[0].resolve(TASKS_OK);
    await Promise.all([p1, p2]);

    expect(spy).toHaveBeenCalledTimes(1);
    expect(store.status).toBe('ready');
    expect(store.tasks).toHaveLength(1);
  });

  it('collapses concurrent loadUsers() calls into exactly one request', async () => {
    const { spy, calls } = deferredFetch();
    vi.stubGlobal('fetch', spy);
    const store = new TasksStore();

    const p1 = store.loadUsers();
    const p2 = store.loadUsers();
    const p3 = store.loadUsers();
    expect(spy).toHaveBeenCalledTimes(1);

    calls[0].resolve(USERS_OK);
    await Promise.all([p1, p2, p3]);

    expect(spy).toHaveBeenCalledTimes(1);
    expect(store.users).toHaveLength(1);
  });

  it('refetches after a settled load (no caching)', async () => {
    const { spy, calls } = deferredFetch();
    vi.stubGlobal('fetch', spy);
    const store = new TasksStore();

    const p1 = store.load();
    calls[0].resolve(TASKS_OK);
    await p1;
    expect(spy).toHaveBeenCalledTimes(1);

    const p2 = store.load();
    expect(spy).toHaveBeenCalledTimes(2);
    calls[1].resolve({ count: 0, tasks: [] });
    await p2;
    expect(store.tasks).toHaveLength(0);
  });

  it('clears the guard after a failed load, sets error, and retries', async () => {
    const { spy, calls } = deferredFetch();
    vi.stubGlobal('fetch', spy);
    const store = new TasksStore();

    const p1 = store.load();
    calls[0].fail(500, 'boom');
    await p1;
    expect(store.status).toBe('error');
    expect(store.error).toBeTruthy();
    expect(spy).toHaveBeenCalledTimes(1);

    const p2 = store.load();
    expect(spy).toHaveBeenCalledTimes(2);
    calls[1].resolve(TASKS_OK);
    await p2;
    expect(store.status).toBe('ready');
  });
});
