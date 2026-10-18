import { describe, it, expect, afterEach, vi } from 'vitest';
import { mount, unmount, flushSync, tick } from 'svelte';
import SettingsAccount from '../../src/components/SettingsAccount.svelte';
import Tasks from '../../src/components/Tasks.svelte';
import TowerDetail from '../../src/components/TowerDetail.svelte';
import MyLeads from '../../src/components/MyLeads.svelte';
import { auth } from '../../src/lib/auth-store.svelte';
import { leads } from '../../src/lib/leads-store.svelte';
import { tasks } from '../../src/lib/tasks-store.svelte';
import { NO_OWNER } from '../../src/lib/nav';
import type { OwnerSummary } from '../../src/lib/leads-api';

// Read-only demo (ADR-077): every write control hides or disables when
// auth.readOnly is set, and is back when it is not.

const TASK = {
  id: 1,
  title: 'Call the owner',
  description: '',
  status: 'open',
  priority: 'none',
  source: 'manual',
  due_date: null,
  assignee_user_id: null,
  lead_cluster_id: null,
  tower_asr: null,
  labels: [],
  created_at: '2026-10-01T00:00:00Z',
  completed_at: null,
  created_by_user_id: null,
};

const ANTENNA = { asr: '1000001', address: '1 Main St', owner_name: '', owner_phone: '', owner_email: '', notes: 'seen', archived: false };

function stubFetch(): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if ((init?.method ?? 'GET') !== 'GET') throw new Error(`unexpected write ${init?.method} ${url}`);
      const body = url.startsWith('/api/tasks')
        ? { tasks: [TASK] }
        : url.startsWith('/api/users')
          ? { users: [] }
          : url.startsWith('/api/antennas/')
            ? ANTENNA
            : null;
      if (body === null) throw new Error(`unexpected fetch ${url}`);
      return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }),
  );
}

let target: HTMLElement;
let app: Record<string, unknown> | null = null;

async function render(component: any, props: Record<string, unknown> = {}): Promise<HTMLElement> {
  target = document.createElement('div');
  document.body.appendChild(target);
  app = mount(component, { target, props });
  flushSync();
  // Let mount-time fetches resolve and re-render.
  for (let i = 0; i < 5; i++) await new Promise((r) => setTimeout(r, 0));
  await tick();
  flushSync();
  return target;
}

const q = (el: HTMLElement, id: string) => el.querySelector<HTMLElement>(`[data-testid="${id}"]`);

afterEach(() => {
  if (app) unmount(app);
  app = null;
  target?.remove();
  auth.readOnly = false;
  leads.myLeads = [];
  tasks.tasks = [];
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('SettingsAccount', () => {
  it('replaces the name and password forms with one line when read-only', async () => {
    auth.readOnly = true;
    const el = await render(SettingsAccount);
    expect(q(el, 'account-read-only')?.textContent).toContain('read-only demo account');
    expect(q(el, 'display-name')).toBeNull();
    expect(q(el, 'display-name-save')).toBeNull();
    expect(q(el, 'password-form')).toBeNull();
    expect(q(el, 'account-email')).not.toBeNull();
  });

  it('shows the forms for a normal user', async () => {
    const el = await render(SettingsAccount);
    expect(q(el, 'account-read-only')).toBeNull();
    expect(q(el, 'display-name')).not.toBeNull();
    expect(q(el, 'password-form')).not.toBeNull();
  });
});

describe('Tasks', () => {
  it('hides create and delete and disables the status controls when read-only', async () => {
    stubFetch();
    auth.readOnly = true;
    const el = await render(Tasks);
    expect(q(el, 'task-row')).not.toBeNull();
    expect(q(el, 'task-form')).toBeNull();
    expect(q(el, 'task-delete')).toBeNull();
    expect((q(el, 'task-check') as HTMLInputElement).disabled).toBe(true);
    expect((q(el, 'task-status') as HTMLButtonElement).disabled).toBe(true);
  });

  it('offers every write control to a normal user', async () => {
    stubFetch();
    const el = await render(Tasks);
    expect(q(el, 'task-form')).not.toBeNull();
    expect(q(el, 'task-delete')).not.toBeNull();
    expect((q(el, 'task-check') as HTMLInputElement).disabled).toBe(false);
    expect((q(el, 'task-status') as HTMLButtonElement).disabled).toBe(false);
  });
});

describe('TowerDetail (unowned tower)', () => {
  const props = { cid: NO_OWNER, asr: ANTENNA.asr };

  it('shows manual details disabled, with no save or archive, when read-only', async () => {
    stubFetch();
    auth.readOnly = true;
    const el = await render(TowerDetail, props);
    const address = q(el, 'manual-address') as HTMLInputElement;
    expect(address.value).toBe('1 Main St');
    expect(address.disabled).toBe(true);
    expect((q(el, 'manual-notes') as HTMLTextAreaElement).disabled).toBe(true);
    expect((q(el, 'manual-owner-name') as HTMLInputElement).disabled).toBe(true);
    expect(q(el, 'manual-save')).toBeNull();
    expect(q(el, 'archive-toggle')).toBeNull();
    expect(q(el, 'no-owner-note')?.textContent).not.toContain('Add owner details');
  });

  it('keeps the editable layer for a normal user', async () => {
    stubFetch();
    const el = await render(TowerDetail, props);
    expect((q(el, 'manual-address') as HTMLInputElement).disabled).toBe(false);
    expect(q(el, 'manual-save')).not.toBeNull();
    expect(q(el, 'archive-toggle')).not.toBeNull();
  });
});

describe('MyLeads kanban', () => {
  const OWNER = {
    display_cluster_id: 'c1',
    owner_name: 'Acme Farms',
    owner_kind: 'individual',
    states: ['AR'],
    tower_count: 1,
    cross_state: false,
    distress_tier: null,
    trigger_asr: null,
    status: 'researching',
  } as unknown as OwnerSummary;

  async function board(): Promise<HTMLElement> {
    leads.myLeads = [{ ...OWNER }];
    leads.myLeadsStatus = 'ready';
    return render(MyLeads);
  }

  it('blocks drag start and drop when read-only', async () => {
    auth.readOnly = true;
    const move = vi.spyOn(leads, 'moveLead');
    const el = await board();
    const card = q(el, 'lead-card')!;
    expect(card.getAttribute('draggable')).toBe('false');

    const start = new Event('dragstart', { cancelable: true });
    card.dispatchEvent(start);
    expect(start.defaultPrevented).toBe(true);

    const lane = el.querySelector<HTMLElement>('[data-lane="contacted"]')!;
    lane.dispatchEvent(new Event('drop', { cancelable: true }));
    await tick();
    expect(move).not.toHaveBeenCalled();
  });

  it('lets a normal user drag a card', async () => {
    const el = await board();
    const card = q(el, 'lead-card')!;
    expect(card.getAttribute('draggable')).toBe('true');
    const start = new Event('dragstart', { cancelable: true });
    card.dispatchEvent(start);
    expect(start.defaultPrevented).toBe(false);
  });
});
