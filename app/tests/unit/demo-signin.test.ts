import { describe, it, expect, afterEach, vi } from 'vitest';
import { mount, unmount, flushSync, tick } from 'svelte';
import SignIn from '../../src/components/SignIn.svelte';
import UserMenu from '../../src/components/UserMenu.svelte';
import { auth } from '../../src/lib/auth-store.svelte';
import { notice } from '../../src/lib/notice.svelte';
import { updateLead } from '../../src/lib/leads-api';

// The public read-only demo (ADR-077): the sign-in page offers "Explore the
// demo" only when the backend says DEMO_MODE is on; a read-only session shows
// the badge; a refused write raises one calm notice.

type Route = (init?: RequestInit) => { status: number; body?: unknown };

function mockFetch(routes: Record<string, Route>) {
  const fn = vi.fn(async (url: string, init?: RequestInit) => {
    const key = `${init?.method ?? 'GET'} ${url}`;
    const route = routes[key];
    if (!route) throw new Error(`unexpected fetch ${key}`);
    const { status, body } = route(init);
    return new Response(body === undefined ? null : JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    });
  });
  vi.stubGlobal('fetch', fn);
  return fn;
}

const ME_DEMO = { tenant_id: 2, email: 'demo', team: 'demo', display_name: '', read_only: true };

let target: HTMLElement;
let app: Record<string, unknown> | null = null;

function render(component: typeof SignIn | typeof UserMenu): HTMLElement {
  target = document.createElement('div');
  document.body.appendChild(target);
  app = mount(component, { target });
  flushSync();
  return target;
}

async function settle(): Promise<void> {
  for (let i = 0; i < 5; i++) await new Promise((r) => setTimeout(r, 0));
  await tick();
  flushSync();
}

afterEach(() => {
  if (app) unmount(app);
  app = null;
  target?.remove();
  auth.signOut();
  vi.unstubAllGlobals();
  auth.demoMode = false;
  notice.dismiss();
});

describe('SignIn demo entry', () => {
  it('shows no demo button when the backend reports demo mode off', async () => {
    mockFetch({ 'GET /api/auth/config': () => ({ status: 200, body: { demo_mode: false } }) });
    const el = render(SignIn);
    await settle();
    expect(el.querySelector('[data-testid="signin-demo"]')).toBeNull();
    expect(el.querySelector('[data-testid="signin-submit"]')?.className).toContain('btn-primary');
  });

  it('hides the demo button when the config call fails', async () => {
    mockFetch({ 'GET /api/auth/config': () => ({ status: 500, body: { detail: 'boom' } }) });
    const el = render(SignIn);
    await settle();
    expect(el.querySelector('[data-testid="signin-demo"]')).toBeNull();
  });

  it('signs in as the read-only demo with one click', async () => {
    const fetch = mockFetch({
      'GET /api/auth/config': () => ({ status: 200, body: { demo_mode: true } }),
      'POST /api/auth/demo': () => ({
        status: 200,
        body: { access_token: 't', token_type: 'bearer', expires_in: 60 },
      }),
      'GET /api/auth/me': () => ({ status: 200, body: ME_DEMO }),
      'POST /api/auth/logout': () => ({ status: 204 }),
    });
    const el = render(SignIn);
    await settle();

    const demo = el.querySelector<HTMLButtonElement>('[data-testid="signin-demo"]');
    expect(demo?.textContent?.trim()).toBe('Explore the demo');
    // The password form stays available, demoted to a secondary action.
    expect(el.querySelector('[data-testid="signin-submit"]')?.className).toContain('btn-secondary');

    demo!.click();
    await settle();

    const calls = fetch.mock.calls.map(([url, init]) => `${init?.method ?? 'GET'} ${url}`);
    expect(calls).toContain('POST /api/auth/demo');
    expect(auth.verified).toBe(true);
    expect(auth.readOnly).toBe(true);
  });

  it('keeps all user-visible copy free of em and en dashes', async () => {
    mockFetch({ 'GET /api/auth/config': () => ({ status: 200, body: { demo_mode: true } }) });
    const el = render(SignIn);
    await settle();
    expect(el.textContent).not.toMatch(/[–—]/);
  });
});

describe('read-only session chrome', () => {
  it('shows the Read-only demo badge only for a read-only principal', () => {
    auth.email = 'demo';
    auth.readOnly = true;
    let el = render(UserMenu);
    expect(el.querySelector('[data-testid="read-only-badge"]')?.textContent?.trim()).toBe(
      'Read-only demo',
    );
    unmount(app!);
    app = null;
    target.remove();

    auth.readOnly = false;
    el = render(UserMenu);
    expect(el.querySelector('[data-testid="read-only-badge"]')).toBeNull();
  });

  it('turns a refused write into one calm notice instead of a crash', async () => {
    const detail = 'This is a read-only demo account. Changes are disabled.';
    mockFetch({ 'PUT /api/leads/abc': () => ({ status: 403, body: { detail } }) });
    await expect(updateLead('abc', { notes: 'x' })).rejects.toMatchObject({ status: 403 });
    expect(notice.message).toBe(detail);
  });
});
