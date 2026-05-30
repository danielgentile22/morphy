<script lang="ts">
  import { onMount } from 'svelte';
  import { app } from './lib/stores.svelte';
  import MapView from './components/MapView.svelte';
  import StateSelector from './components/StateSelector.svelte';
  import SummaryCard from './components/SummaryCard.svelte';
  import LayerPanel from './components/LayerPanel.svelte';
  import Legend from './components/Legend.svelte';
  import TopFilterBar from './components/TopFilterBar.svelte';
  import DetailsPanel from './components/DetailsPanel.svelte';
  import Candidates from './components/Candidates.svelte';
  import MyLeads from './components/MyLeads.svelte';
  import LeadPage from './components/LeadPage.svelte';
  import SignIn from './components/SignIn.svelte';
  import { leads } from './lib/leads-store.svelte';
  import { auth } from './lib/auth-store.svelte';
  import { buildUrl } from './lib/url';

  // Captured synchronously, before any effect can rewrite the URL.
  const initialSearch = location.search;

  let showHelp = $state(false);

  // Lightweight hash routing layered over the existing map app. The map
  // (`.layout`) stays mounted; the Lead surfaces render as an overlay on
  // top for #/candidates and #/lead/:key, so switching never tears down
  // MapLibre/DuckDB (ADR-061: the map instance persists across routes).
  type Route =
    | { name: 'map' }
    | { name: 'candidates' }
    | { name: 'leads' }
    | { name: 'lead'; key: string };
  function parseRoute(): Route {
    const parts = location.hash.replace(/^#\/?/, '').split('/').filter(Boolean);
    if (parts[0] === 'lead' && parts[1]) return { name: 'lead', key: decodeURIComponent(parts[1]) };
    if (parts[0] === 'leads') return { name: 'leads' };
    if (parts[0] === 'candidates') return { name: 'candidates' };
    return { name: 'map' };
  }
  let route = $state<Route>(parseRoute());
  function goMap(): void {
    location.hash = '';
  }
  function goCandidates(): void {
    location.hash = '#/candidates';
  }
  function goLeads(): void {
    location.hash = '#/leads';
  }

  // Keep the Candidates count badge fresh once we're on a Lead surface
  // (covers a deep link straight to #/lead/:key without visiting the list).
  // Gated on auth — the Lead routes require a signed-in session.
  $effect(() => {
    if (route.name !== 'map' && auth.signedIn && leads.candidatesStatus === 'idle') {
      void leads.loadCandidates();
    }
  });

  // Live nav counts — load once signed in and on every sign-in transition, so
  // the Candidates / My-Leads badges are correct on every surface (incl. the
  // map launchers) before either list is opened.
  $effect(() => {
    if (auth.signedIn) void leads.loadCounts();
  });

  /** True when the event originates from a text-entry control — keyboard
   *  shortcuts (including Escape) stay inert so they don't hijack typing. */
  function isTypingTarget(e: KeyboardEvent): boolean {
    const el = e.target;
    return (
      el instanceof HTMLElement &&
      (el.tagName === 'INPUT' ||
        el.tagName === 'SELECT' ||
        el.tagName === 'TEXTAREA' ||
        el.isContentEditable)
    );
  }

  function onKeydown(e: KeyboardEvent): void {
    // Inert while typing — e.g. Escape in the owner-search box must clear
    // the field, not the map selection.
    if (isTypingTarget(e)) return;
    if (e.key === 'Escape') {
      if (showHelp) showHelp = false;
      else app.clearSelection();
    } else if (e.key === 'f') {
      e.preventDefault();
      document.querySelector<HTMLInputElement>('[data-testid="owner-search"]')?.focus();
    } else if (e.key === '?') {
      showHelp = !showHelp;
    }
  }

  function onHashChange(): void {
    route = parseRoute();
  }

  onMount(() => {
    void app.boot(initialSearch);
    // Validate any persisted JWT (populates the signed-in email; a stale
    // token is dropped via a 401, falling back to the sign-in surface).
    void auth.loadMe();
    window.addEventListener('keydown', onKeydown);
    window.addEventListener('hashchange', onHashChange);
    return () => {
      window.removeEventListener('keydown', onKeydown);
      window.removeEventListener('hashchange', onHashChange);
    };
  });

  // Keep the URL a shareable deep link — state, selected parcel, filters.
  // Gated on urlSyncReady so it cannot erase the deep-link before boot
  // has restored it. Skipped on the Lead routes so it never strips the hash.
  $effect(() => {
    if (route.name !== 'map') return;
    if (!app.urlSyncReady) return;
    const sel = app.selection;
    const selectedId =
      sel?.kind === 'parcel' && typeof sel.props.parcel_id === 'string'
        ? sel.props.parcel_id
        : null;
    const next = buildUrl(location.pathname, app.activeFips, selectedId, app.filters);
    if (next !== location.pathname + location.search) {
      history.replaceState(null, '', next);
    }
  });
</script>

<div class="layout">
  <aside class="sidebar">
    <header class="app-header">
      <h1>{app.activeState?.name ?? 'Pilot Map'}</h1>
      <p class="subtitle">Parcels &amp; infrastructure — renegotiation candidates</p>
    </header>

    {#if app.notice}
      <div class="notice" role="status">
        <span>{app.notice}</span>
        <button class="notice-close" onclick={() => app.dismissNotice()} aria-label="Dismiss">
          ×
        </button>
      </div>
    {/if}

    <div class="sidebar-scroll">
      <section class="panel">
        <StateSelector />
      </section>
      {#if app.status === 'ready'}
        <SummaryCard />
        <LayerPanel />
        <Legend />
      {/if}
    </div>

    <footer class="app-footer">
      Prototype · local use only · data is PII (owner names + addresses)
    </footer>
  </aside>

  <main class="stage">
    {#if app.status === 'error'}
      <div class="error-screen" data-testid="boot-error">
        <div class="error-card">
          <h2>Could not load the map data</h2>
          <p class="error-detail">{app.errorMessage}</p>
          <p class="error-hint">
            Start the range-capable data server from the repo root
            (<code>python scripts/serve.py 8765</code>), then retry.
          </p>
          <button class="retry" onclick={() => app.boot(initialSearch)}>Retry</button>
        </div>
      </div>
    {:else}
      {#if app.status === 'ready'}
        <TopFilterBar />
      {/if}
      <div class="map-wrap">
        <MapView />
        <DetailsPanel />
        <div class="launchers">
          <button class="launcher" data-testid="open-candidates" onclick={goCandidates}>
            Candidates{#if leads.candidatesCount}
              <span class="lc-badge">{leads.candidatesCount}</span>
            {/if}
          </button>
          <button class="launcher" data-testid="open-my-leads-map" onclick={goLeads}>
            My Leads{#if leads.myLeadsCount}
              <span class="lc-badge">{leads.myLeadsCount}</span>
            {/if}
          </button>
        </div>
        {#if app.status === 'loading'}
          <div class="loading-pill" data-testid="loading">Loading…</div>
        {/if}
      </div>
    {/if}
  </main>

  {#if route.name !== 'map'}
    <div class="lead-overlay" data-testid="lead-overlay">
      <nav class="lead-nav">
        <span class="brand">Ground-Lease Triage</span>
        <button class="navtab" onclick={goMap}>Map</button>
        <button class="navtab" class:on={route.name === 'candidates'} onclick={goCandidates}>
          Candidates
          {#if leads.candidatesCount}<span class="lc-badge">{leads.candidatesCount}</span>{/if}
        </button>
        <button
          class="navtab"
          class:on={route.name === 'leads'}
          data-testid="open-my-leads"
          onclick={goLeads}
        >
          My Leads
          {#if leads.myLeadsCount}<span class="lc-badge">{leads.myLeadsCount}</span>{/if}
        </button>
        {#if auth.signedIn}
          <span class="nav-user" data-testid="nav-user">{auth.email ?? 'signed in'}</span>
          <button class="navtab signout" data-testid="signout" onclick={() => auth.signOut()}>
            Sign out
          </button>
        {:else}
          <span class="nav-note">Lead = one cross-state landowner · ADR-061</span>
        {/if}
      </nav>
      {#if auth.signedIn && route.name === 'candidates'}
        <TopFilterBar />
      {/if}
      <div class="lead-content">
        {#if !auth.signedIn}
          <SignIn />
        {:else if route.name === 'candidates'}
          <Candidates />
        {:else if route.name === 'leads'}
          <MyLeads />
        {:else if route.name === 'lead'}
          <LeadPage displayClusterId={route.key} />
        {/if}
      </div>
    </div>
  {/if}

  {#if showHelp}
    <div class="help-overlay" role="dialog" aria-label="Keyboard shortcuts" data-testid="help">
      <div class="help-card">
        <button class="help-close" onclick={() => (showHelp = false)} aria-label="Close help">
          ×
        </button>
        <h2>Keyboard shortcuts</h2>
        <dl>
          <dt>f</dt>
          <dd>Focus owner search</dd>
          <dt>Esc</dt>
          <dd>Clear the selected parcel</dd>
          <dt>?</dt>
          <dd>Toggle this help</dd>
        </dl>
      </div>
    </div>
  {/if}
</div>

<style>
  .layout {
    display: flex;
    height: 100%;
  }

  .sidebar {
    width: var(--sidebar-w);
    flex-shrink: 0;
    background: var(--panel);
    border-right: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    z-index: 10;
  }

  .app-header {
    padding: 16px 18px 12px;
    border-bottom: 1px solid var(--border);
  }
  .app-header h1 {
    font-size: 18px;
  }
  .subtitle {
    margin: 3px 0 0;
    font-size: 12px;
    color: var(--muted);
  }

  .notice {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    padding: 8px 14px;
    background: #fff7e6;
    border-bottom: 1px solid #f0d9a8;
    font-size: 12px;
    color: #7a5b00;
  }
  .notice-close {
    margin-left: auto;
    background: none;
    border: none;
    font-size: 16px;
    line-height: 1;
    color: inherit;
  }

  .sidebar-scroll {
    flex: 1;
    overflow-y: auto;
  }
  .panel {
    padding: 14px 18px;
    border-bottom: 1px solid var(--border);
  }

  .app-footer {
    padding: 10px 18px;
    font-size: 11px;
    color: var(--muted);
    border-top: 1px solid var(--border);
  }

  .stage {
    flex: 1;
    position: relative;
    display: flex;
    flex-direction: column;
    background: var(--panel-2);
  }
  /* Holds the absolutely-positioned map + its overlays, below the top filter
     bar (which sits in normal flow at the top of the stage). */
  .map-wrap {
    flex: 1;
    position: relative;
  }

  .loading-pill {
    position: absolute;
    top: 12px;
    left: 50%;
    transform: translateX(-50%);
    z-index: 20;
    padding: 6px 14px;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 999px;
    font-size: 12px;
    color: var(--muted);
    box-shadow: var(--shadow);
  }

  /* Entry points into the Lead surfaces. Top-left of the map stage, clear
     of the sidebar and the top-right details panel. */
  .launchers {
    position: absolute;
    top: 12px;
    left: 12px;
    z-index: 20;
    display: flex;
    gap: 8px;
  }
  .launcher {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 7px 14px;
    background: var(--accent);
    color: #fff;
    border: none;
    border-radius: 999px;
    font-size: 12.5px;
    font-weight: 600;
    box-shadow: var(--shadow);
  }
  .lc-badge {
    background: rgba(255, 255, 255, 0.28);
    border-radius: 999px;
    padding: 0 6px;
    font-size: 11px;
  }

  .lead-overlay {
    position: fixed;
    inset: 0;
    z-index: 40;
    background: var(--bg);
    display: flex;
    flex-direction: column;
  }
  .lead-nav {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 9px 18px;
    background: var(--panel);
    border-bottom: 1px solid var(--border);
  }
  .lead-nav .brand {
    font-weight: 600;
    font-size: 14px;
    margin-right: 6px;
  }
  .navtab {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 5px 12px;
    border: 1px solid var(--border);
    background: var(--panel);
    color: var(--text-2);
    border-radius: 999px;
    font-size: 12.5px;
  }
  .navtab.on {
    background: var(--accent);
    border-color: var(--accent);
    color: #fff;
  }
  .nav-note {
    margin-left: auto;
    font-size: 11px;
    color: var(--muted);
  }
  .nav-user {
    margin-left: auto;
    font-size: 12px;
    color: var(--text-2);
  }
  .navtab.signout {
    color: var(--text-2);
  }
  .lead-content {
    flex: 1;
    overflow-y: auto;
  }

  .error-screen {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24px;
  }
  .error-card {
    max-width: 460px;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 22px 24px;
    box-shadow: var(--shadow);
  }
  .error-card h2 {
    font-size: 16px;
    margin-bottom: 8px;
  }
  .error-detail {
    font-size: 13px;
    color: var(--danger);
    word-break: break-word;
  }
  .error-hint {
    font-size: 12px;
    color: var(--muted);
  }
  .error-hint code {
    font-family: var(--mono);
    background: var(--panel-2);
    padding: 1px 5px;
    border-radius: 3px;
  }
  .retry {
    margin-top: 8px;
    padding: 7px 16px;
    border: 1px solid var(--accent);
    background: var(--accent);
    color: #fff;
    border-radius: var(--radius);
    font-size: 13px;
  }

  .help-overlay {
    position: fixed;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(20, 24, 31, 0.4);
    z-index: 50;
  }
  .help-card {
    position: relative;
    background: var(--panel);
    border-radius: var(--radius);
    padding: 20px 26px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.25);
    min-width: 260px;
  }
  .help-card h2 {
    font-size: 13px;
    margin: 0 0 12px;
  }
  .help-card dl {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 6px 14px;
    margin: 0;
    font-size: 13px;
  }
  .help-card dt {
    font-family: var(--mono);
    background: var(--panel-2);
    padding: 1px 7px;
    border-radius: 3px;
    justify-self: start;
  }
  .help-card dd {
    margin: 0;
    color: var(--text-2);
  }
  .help-close {
    position: absolute;
    top: 8px;
    right: 10px;
    border: none;
    background: none;
    font-size: 18px;
    line-height: 1;
    color: var(--muted);
  }

  /* Visible keyboard-focus ring for accessibility. */
  :global(:focus-visible) {
    outline: 2px solid var(--accent);
    outline-offset: 1px;
  }
</style>
