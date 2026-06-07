<script lang="ts">
  import { onMount } from 'svelte';
  import { app } from './lib/stores.svelte';
  import MapView from './components/MapView.svelte';
  import StateSelector from './components/StateSelector.svelte';
  import SummaryCard from './components/SummaryCard.svelte';
  import LayerPanel from './components/LayerPanel.svelte';
  import TopFilterBar from './components/TopFilterBar.svelte';
  import DetailsPanel from './components/DetailsPanel.svelte';
  import Dashboard from './components/Dashboard.svelte';
  import Leads from './components/Leads.svelte';
  import LeadPage from './components/LeadPage.svelte';
  import ExploreList from './components/ExploreList.svelte';
  import TowerDetail from './components/TowerDetail.svelte';
  import ScoringPanel from './components/ScoringPanel.svelte';
  import SignIn from './components/SignIn.svelte';
  import { leads } from './lib/leads-store.svelte';
  import { dashboard } from './lib/dashboard-store.svelte';
  import { archivedAntennas } from './lib/archived-antennas.svelte';
  import { auth } from './lib/auth-store.svelte';
  import { buildUrl } from './lib/url';
  import {
    parseRoute,
    sectionOf,
    SECTION_HASH,
    type Route,
    type Section,
  } from './lib/nav';

  // Captured synchronously, before any effect can rewrite the URL.
  const initialSearch = location.search;

  let showHelp = $state(false);

  // Three-section hash routing (UI overhaul P1 / #104, ADR-065):
  // Dashboard · Explore · Leads, with Dashboard sub-pages. The Explore map
  // layout stays mounted at all times — the other sections render as an
  // opaque surface on top of it — so MapLibre/DuckDB never tear down on a
  // nav (ADR-061 map persistence). The app opens on the Dashboard.
  let route = $state<Route>(parseRoute(location.hash));
  let section = $derived<Section>(sectionOf(route));
  // Explore's two lenses (#108): the map and the ranked tower list. The map
  // stays mounted; the list renders over it.
  let exploreView = $state<'map' | 'list'>('map');
  function go(section: Section): void {
    location.hash = SECTION_HASH[section];
  }

  // Boot the data layer only once a *verified* session exists (#85): no data
  // fetch (index, towers, parcels, counts) may fire before sign-in. Boot runs
  // once per page load; signing out unmounts the app but keeps loaded state,
  // and signing back in re-renders from it.
  let booted = false;
  $effect(() => {
    if (auth.verified && !booted) {
      booted = true;
      void app.boot(initialSearch);
    }
  });

  // Live nav counts + attention badge — load once signed in and on every
  // sign-in transition, so the Explore / Leads / Dashboard badges are correct.
  $effect(() => {
    if (auth.verified) {
      void leads.loadCounts();
      void dashboard.loadAttention();
      // The set of archived antennas the map + list exclude (round 2).
      void archivedAntennas.hydrate();
    }
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
    // Shortcuts only exist inside the app — inert on the sign-in gate (#85),
    // so e.g. '?' can't queue up a help overlay for after sign-in.
    if (!auth.verified) return;
    // Inert while typing — e.g. Escape in the owner-search box must clear
    // the field, not the map selection.
    if (isTypingTarget(e)) return;
    if (e.key === '?') {
      showHelp = !showHelp;
      return;
    }
    if (e.key === 'Escape' && showHelp) {
      showHelp = false;
      return;
    }
    // The map-centric shortcuts only act inside Explore (where the map lives).
    if (section !== 'explore') return;
    if (e.key === 'Escape') {
      app.clearSelection();
    } else if (e.key === 'f') {
      e.preventDefault();
      document.querySelector<HTMLInputElement>('[data-testid="owner-search"]')?.focus();
    }
  }

  function onHashChange(): void {
    route = parseRoute(location.hash);
  }

  onMount(() => {
    // Validate any persisted JWT (populates the signed-in email; a stale
    // token is dropped via a 401, leaving the full-screen sign-in gate up).
    // The data layer boots from the $effect above only after verification.
    void auth.loadMe();
    window.addEventListener('keydown', onKeydown);
    window.addEventListener('hashchange', onHashChange);
    return () => {
      window.removeEventListener('keydown', onKeydown);
      window.removeEventListener('hashchange', onHashChange);
    };
  });

  // Keep the URL a shareable deep link — state, selected parcel, filters live
  // in the query string; the section lives in the hash. Only sync while in
  // Explore (the map), and always preserve the section hash so the sync never
  // strips it. Gated on urlSyncReady so it can't erase the deep-link before
  // boot has restored it.
  $effect(() => {
    if (section !== 'explore') return;
    if (!app.urlSyncReady) return;
    const sel = app.selection;
    const selectedId =
      sel?.kind === 'parcel' && typeof sel.props.parcel_id === 'string'
        ? sel.props.parcel_id
        : null;
    const next =
      buildUrl(location.pathname, app.activeFips, selectedId, app.filters) + location.hash;
    if (next !== location.pathname + location.search + location.hash) {
      history.replaceState(null, '', next);
    }
  });
</script>

{#if !auth.verified}
  <!-- Full-screen sign-in gate (#85): until a verified session exists, nothing
       else mounts — no map, no navigation, no panels, no data fetches. The
       SignIn card carries the Morphy Consulting branding (round 2 cleanup). -->
  <div class="gate" data-testid="auth-gate">
    {#if auth.restoring}
      <p class="gate-checking" data-testid="gate-checking">Checking session…</p>
    {:else}
      <SignIn />
    {/if}
  </div>
{:else}
  <div class="shell">
    <nav class="topnav" data-testid="topnav">
      <span class="brand">Ground-Lease Triage</span>
      <div class="tabs" role="tablist" aria-label="Sections">
        <button
          class="tab"
          class:on={section === 'dashboard'}
          data-testid="nav-dashboard"
          role="tab"
          aria-selected={section === 'dashboard'}
          onclick={() => go('dashboard')}
        >
          Dashboard{#if dashboard.count}<span class="nbadge" data-testid="attention-badge">{dashboard.count}</span>{/if}
        </button>
        <button
          class="tab"
          class:on={section === 'explore'}
          data-testid="nav-explore"
          role="tab"
          aria-selected={section === 'explore'}
          onclick={() => go('explore')}
        >
          Explore{#if leads.candidatesCount}<span class="nbadge">{leads.candidatesCount}</span>{/if}
        </button>
        <button
          class="tab"
          class:on={section === 'leads'}
          data-testid="nav-leads"
          role="tab"
          aria-selected={section === 'leads'}
          onclick={() => go('leads')}
        >
          Leads{#if leads.myLeadsCount}<span class="nbadge">{leads.myLeadsCount}</span>{/if}
        </button>
      </div>
      <span class="nav-user" data-testid="nav-user">
        {auth.team ? `${auth.email} · ${auth.team}` : auth.email}
      </span>
      <button class="signout" data-testid="signout" onclick={() => auth.signOut()}>Sign out</button>
    </nav>

    <div class="shell-body">
      <!-- Explore: the map layout stays mounted at all times so MapLibre /
           DuckDB never tear down on a section change (ADR-061 / #104). The
           other sections render as an opaque surface over it (below). -->
      <div class="explore-layout">
        <aside class="sidebar">
          <header class="app-header">
            <h1>{app.activeState?.name ?? 'Explore'}</h1>
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
              <ScoringPanel />
              <LayerPanel />
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
        {#if app.status === 'ready' && section === 'explore'}
          <!-- The top filter bar drives the Explore map + tower list only.
               Dashboard/Leads/Lead have their own (or no) filtering, so the
               bar is gated to Explore — elsewhere it was dead and overlapped
               the page heading. -->
          <TopFilterBar />
          {#if route.name === 'explore'}
            <div class="explore-views" role="tablist" aria-label="Explore view">
              <button
                class="vbtn"
                class:on={exploreView === 'map'}
                data-testid="explore-view-map"
                role="tab"
                aria-selected={exploreView === 'map'}
                onclick={() => (exploreView = 'map')}
              >
                Map
              </button>
              <button
                class="vbtn"
                class:on={exploreView === 'list'}
                data-testid="explore-view-list"
                role="tab"
                aria-selected={exploreView === 'list'}
                onclick={() => (exploreView = 'list')}
              >
                List
              </button>
            </div>
          {/if}
        {/if}
        <div class="map-wrap">
          <MapView />
          <DetailsPanel />
          {#if app.status === 'loading'}
            <div class="loading-pill" data-testid="loading">Loading…</div>
          {/if}
          <!-- Tower-grained Explore (#108): the ranked list and a tower's
               read-only detail peek render over the still-mounted map. -->
          {#if route.name === 'tower'}
            <div class="explore-overlay" data-testid="explore-overlay">
              <TowerDetail cid={route.cid} asr={route.asr} />
            </div>
          {:else if route.name === 'explore' && exploreView === 'list'}
            <div class="explore-overlay" data-testid="explore-overlay">
              <ExploreList />
            </div>
          {/if}
        </div>
      {/if}
        </main>
      </div>

      <!-- Dashboard / Leads / owner page render over the (still-mounted) map. -->
      {#if section !== 'explore'}
        <div class="surface" data-testid="section-surface">
          {#if route.name === 'dashboard'}
            <Dashboard sub={route.sub} />
          {:else if route.name === 'leads'}
            <Leads />
          {:else if route.name === 'lead'}
            <LeadPage displayClusterId={route.key} />
          {/if}
        </div>
      {/if}
    </div>

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
{/if}

<style>
  /* Full-screen sign-in gate (#85): the only surface an unauthenticated
     visitor ever sees. */
  .gate {
    height: 100%;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 4px;
    background: var(--bg);
  }
  .gate-checking {
    margin-top: 24px;
    font-size: 13px;
    color: var(--muted);
  }

  /* Three-section shell (#104): a fixed top nav over a body that holds the
     always-mounted Explore map layout + the section surfaces. */
  .shell {
    display: flex;
    flex-direction: column;
    height: 100%;
  }
  .topnav {
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 9px 18px;
    background: var(--panel);
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
    z-index: 30;
  }
  .topnav .brand {
    font-weight: 600;
    font-size: 14px;
  }
  .tabs {
    display: flex;
    gap: 6px;
  }
  .tab {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 6px 14px;
    border: 1px solid var(--border);
    background: var(--panel);
    color: var(--text-2);
    border-radius: 999px;
    font-size: 13px;
    font-weight: 600;
  }
  .tab.on {
    background: var(--accent);
    border-color: var(--accent);
    color: #fff;
  }
  .nbadge {
    background: var(--panel-2);
    border-radius: 999px;
    padding: 0 7px;
    font-size: 11px;
    color: var(--text-2);
  }
  .tab.on .nbadge {
    background: rgba(255, 255, 255, 0.28);
    color: #fff;
  }
  .nav-user {
    margin-left: auto;
    font-size: 12px;
    color: var(--text-2);
  }
  .signout {
    background: none;
    border: none;
    padding: 0;
    font-size: 12px;
    color: var(--muted);
    text-decoration: underline;
    cursor: pointer;
  }
  .shell-body {
    flex: 1;
    position: relative;
    min-height: 0;
  }
  /* The map layout fills the body and is never unmounted. */
  .explore-layout {
    display: flex;
    height: 100%;
  }
  /* A section other than Explore: an opaque panel covering the map, which
     stays mounted underneath (so returning to Explore keeps pan/zoom). */
  .surface {
    position: absolute;
    inset: 0;
    z-index: 20;
    background: var(--bg);
    overflow: hidden;
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
  /* Explore map/list toggle — a thin bar under the filter bar. */
  .explore-views {
    display: flex;
    gap: 6px;
    padding: 6px 12px;
    border-bottom: 1px solid var(--border);
    background: var(--panel);
  }
  .explore-views .vbtn {
    padding: 4px 14px;
    font-size: 12.5px;
    border: 1px solid var(--border-strong);
    background: var(--panel);
    color: var(--text-2);
    border-radius: 999px;
  }
  .explore-views .vbtn.on {
    background: var(--accent);
    border-color: var(--accent);
    color: #fff;
  }
  /* The Explore list / tower detail, layered over the still-mounted map. */
  .explore-overlay {
    position: absolute;
    inset: 0;
    z-index: 15;
    background: var(--bg);
    overflow: hidden;
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
