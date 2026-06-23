<script lang="ts">
  import { onMount } from 'svelte';
  import { app } from './lib/stores.svelte';
  import FilterPanel from './components/FilterPanel.svelte';
  import StatStrip from './components/StatStrip.svelte';
  import DetailsPanel from './components/DetailsPanel.svelte';
  import Dashboard from './components/Dashboard.svelte';
  import ScoringPanel from './components/ScoringPanel.svelte';
  import SignIn from './components/SignIn.svelte';
  import UserMenu from './components/UserMenu.svelte';
  // Off-first-paint route components are dynamically imported at their render
  // sites (PERF-012) so they land in their own chunks instead of the entry
  // bundle: Leads, LeadPage, ExploreList, TowerDetail, Settings. Dashboard stays
  // eager — it's the landing view. (Pairs with the PERF-004 manualChunks split.)
  import { leads } from './lib/leads-store.svelte';
  import { dashboard } from './lib/dashboard-store.svelte';
  import { archivedAntennas } from './lib/archived-antennas.svelte';
  import { filterModel } from './lib/filter-model.svelte';
  import { shouldApplyFilterDefault, deserializeFilterModel } from './lib/filter-model';
  import { auth } from './lib/auth-store.svelte';
  import { userSettings } from './lib/user-settings-store.svelte';
  import { prefetchMapData } from './lib/boot-prefetch';
  import { readUrlState } from './lib/url';
  import {
    parseRoute,
    sectionOf,
    SECTION_HASH,
    type Route,
    type Section,
  } from './lib/nav';

  let showHelp = $state(false);

  // Collapsible filter sidebar (#119): collapse it for a bigger map once
  // filters are set; the choice persists across reloads.
  const SIDEBAR_KEY = 'explore.sidebarCollapsed';
  function readCollapsed(): boolean {
    try {
      return localStorage.getItem(SIDEBAR_KEY) === '1';
    } catch {
      return false;
    }
  }
  let sidebarCollapsed = $state(readCollapsed());
  $effect(() => {
    try {
      localStorage.setItem(SIDEBAR_KEY, sidebarCollapsed ? '1' : '0');
    } catch {
      // Private-mode / storage-disabled — collapse just won't persist.
    }
  });

  // Three-section hash routing (UI overhaul P1 / #104, ADR-065):
  // Dashboard · Explore · Leads, with Dashboard sub-pages. The Explore map
  // layout stays mounted at all times — the other sections render as an
  // opaque surface on top of it — so MapLibre/DuckDB never tear down on a
  // nav (ADR-061 map persistence). The app opens on the Dashboard.
  let route = $state<Route>(parseRoute(location.hash));
  let section = $derived<Section>(sectionOf(route));
  // The Settings page is reached from the user menu, not a primary tab — so no
  // top-nav tab is active while it's open (PRD #121).
  let navSection = $derived<Section | null>(route.name === 'settings' ? null : section);
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
      void app.boot();
    }
  });

  // Lazily reveal + boot the heavy Explore map stack only once the user actually
  // reaches a map-bearing route (PERF-001): MapView + the filter sidebar mount,
  // and app.bootMap() pulls the tower parquet + parcel tiles. A Dashboard
  // landing never pays for any of it. Once shown the map is never unmounted
  // (ADR-061 map persistence), so this latch only ever flips false → true.
  let mapEverShown = $state(false);
  $effect(() => {
    if (!auth.verified) return;
    if (section === 'explore' || route.name === 'tower' || route.name === 'lead') {
      mapEverShown = true;
      void app.bootMap();
    }
  });

  // Load the signed-in user's prefs (PRD #121), then apply a saved filter
  // default to Explore — but only when the URL carries no filters of its own,
  // so a shared deep link always wins.
  async function bootUserSettings(): Promise<void> {
    await userSettings.load();
    const s = userSettings.settings;
    const urlHasFilters = readUrlState(location.search).hasFilters;
    if (s.filter_default && shouldApplyFilterDefault(urlHasFilters, s.filter_default_apply)) {
      filterModel.updateFilter(deserializeFilterModel(s.filter_default));
    }
  }

  // Live nav counts + attention badge — load once signed in and on every
  // sign-in transition, so the Explore / Leads / Dashboard badges are correct.
  // The per-user settings load lives here too (not behind `booted`), so a
  // second user signing in on the same page load gets *their* prefs, never the
  // first user's (PRD #121).
  $effect(() => {
    if (auth.verified) {
      void leads.loadCounts();
      void dashboard.loadAttention();
      // The set of archived antennas the map + list exclude (round 2).
      void archivedAntennas.hydrate();
      void bootUserSettings();
    }
  });

  // Warm the heavy Explore map (towers + parcel-tile probes) and the owners
  // filter index DURING the Dashboard, so opening Explore is instant (#168 /
  // PRD #163 M3). Idle-gated so the Dashboard-critical fetches above (counts,
  // attention, settings) win the network first; idempotent via the stores' own
  // latches (`mapBooted` / `ownersStatus`), so the Explore-route `bootMap()`
  // trigger and `FilterPanel.onMount` load become no-ops — no new state machine,
  // no double-load. Fire-and-forget: a failed/aborted warm never touches
  // Dashboard state, and a session that never opens the map just leaves the
  // warmed data unused. Fires once per verified session.
  let mapPrefetched = false;
  $effect(() => {
    if (auth.verified && !mapPrefetched) {
      mapPrefetched = true;
      prefetchMapData();
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
    // Validate the session cookie (populates the signed-in email; no session
    // surfaces as a 401, leaving the full-screen sign-in gate up). The data
    // layer boots from the $effect above only after verification.
    void auth.loadMe();
    window.addEventListener('keydown', onKeydown);
    window.addEventListener('hashchange', onHashChange);
    return () => {
      window.removeEventListener('keydown', onKeydown);
      window.removeEventListener('hashchange', onHashChange);
    };
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
      <span class="brand"><span class="brand-mark" aria-hidden="true"></span>Ground-Lease Triage</span>
      <div class="tabs" role="tablist" aria-label="Sections">
        <button
          class="tab"
          class:on={navSection === 'dashboard'}
          data-testid="nav-dashboard"
          role="tab"
          aria-selected={navSection === 'dashboard'}
          onclick={() => go('dashboard')}
        >
          Dashboard{#if dashboard.count}<span class="nbadge" data-testid="attention-badge">{dashboard.count}</span>{/if}
        </button>
        <button
          class="tab"
          class:on={navSection === 'explore'}
          data-testid="nav-explore"
          role="tab"
          aria-selected={navSection === 'explore'}
          onclick={() => go('explore')}
        >
          Explore{#if leads.candidatesCount}<span class="nbadge">{leads.candidatesCount}</span>{/if}
        </button>
        <button
          class="tab"
          class:on={navSection === 'leads'}
          data-testid="nav-leads"
          role="tab"
          aria-selected={navSection === 'leads'}
          onclick={() => go('leads')}
        >
          Leads{#if leads.myLeadsCount}<span class="nbadge">{leads.myLeadsCount}</span>{/if}
        </button>
      </div>
      <UserMenu />
    </nav>

    <div class="shell-body">
      <!-- Explore: the map layout stays mounted at all times so MapLibre /
           DuckDB never tear down on a section change (ADR-061 / #104). The
           other sections render as an opaque surface over it (below). -->
      <div class="explore-layout">
        {#if sidebarCollapsed}
          <!-- Collapsed rail: one-click re-open, showing the active-filter count
               so the user knows filters are still applied (#119, stories 2–3). -->
          <button
            class="sidebar-rail"
            data-testid="sidebar-open"
            onclick={() => (sidebarCollapsed = false)}
            title="Show filters"
          >
            <span class="rail-icon" aria-hidden="true">»</span>
            <span class="rail-label">
              Filters{#if filterModel.activeCount}<span class="rail-badge">{filterModel.activeCount}</span>{/if}
            </span>
          </button>
        {:else}
          <aside class="sidebar" data-testid="sidebar">
            <header class="app-header">
              <h1>Explore</h1>
              <button
                class="collapse"
                data-testid="sidebar-collapse"
                onclick={() => (sidebarCollapsed = true)}
                aria-label="Collapse filters"
                title="Collapse"
              >
                «
              </button>
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
              <!-- Deferred with the map (PERF-001): FilterPanel.onMount is what
                   eagerly fetches the 10.6 MB owners filter index, so it must not
                   mount on the Dashboard landing. -->
              {#if mapEverShown}
                <StatStrip />
                <FilterPanel />
                {#if app.status === 'ready'}
                  <ScoringPanel />
                {/if}
              {/if}
            </div>
          </aside>
        {/if}

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
            <button class="retry" onclick={() => app.boot()}>Retry</button>
          </div>
        </div>
      {:else}
        {#if app.status === 'ready' && route.name === 'explore'}
          <!-- Map/List lens toggle stays at the top, independent of the filter
               panel's collapsed state (#119, story 4). -->
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
        <div class="map-wrap">
          <!-- The map only ever mounts after the first map-bearing route (PERF-001);
               it then persists for the session (ADR-061). Lazy-imported so the
               MapLibre + DuckDB chunk (and maplibre CSS, PERF-036) stay off the
               landing critical path. -->
          {#if mapEverShown}
            {#await import('./components/MapView.svelte') then m}
              <m.default />
            {/await}
          {/if}
          <DetailsPanel />
          {#if app.status === 'loading' || app.towersStatus === 'loading'}
            <div class="loading-pill" data-testid="loading">Loading…</div>
          {/if}
          <!-- Tower-grained Explore (#108): the ranked list and a tower's
               read-only detail peek render over the still-mounted map. Both are
               lazy-loaded (PERF-012). -->
          {#if route.name === 'tower'}
            <div class="explore-overlay" data-testid="explore-overlay">
              {#await import('./components/TowerDetail.svelte') then m}
                <m.default cid={route.cid} asr={route.asr} />
              {/await}
            </div>
          {:else if route.name === 'explore' && exploreView === 'list'}
            <div class="explore-overlay" data-testid="explore-overlay">
              {#await import('./components/ExploreList.svelte') then m}
                <m.default />
              {/await}
            </div>
          {/if}
        </div>
      {/if}
        </main>
      </div>

      <!-- Dashboard / Leads / owner page render over the (still-mounted) map. -->
      {#if section !== 'explore'}
        <div class="surface" data-testid="section-surface">
          {#if route.name === 'settings'}
            {#await import('./components/Settings.svelte') then m}
              <m.default />
            {/await}
          {:else if route.name === 'dashboard'}
            <Dashboard sub={route.sub} />
          {:else if route.name === 'leads'}
            {#await import('./components/Leads.svelte') then m}
              <m.default />
            {/await}
          {:else if route.name === 'lead'}
            {#await import('./components/LeadPage.svelte') then m}
              <m.default displayClusterId={route.key} />
            {/await}
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
    display: inline-flex;
    align-items: center;
    gap: 9px;
    font-weight: 600;
    font-size: 14px;
  }
  /* Halo conic brand mark. */
  .brand-mark {
    width: 22px;
    height: 22px;
    flex-shrink: 0;
    border-radius: var(--radius-sm);
    border: 1px solid var(--color-border-strong);
    background: conic-gradient(
      from 220deg at 50% 50%,
      var(--color-primary),
      #1e2029,
      var(--color-primary)
    );
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
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 14px 16px;
    border-bottom: 1px solid var(--border);
  }
  .app-header h1 {
    font-size: 18px;
  }
  .collapse {
    margin-left: auto;
    width: 26px;
    height: 26px;
    flex-shrink: 0;
    font-size: 16px;
    line-height: 1;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    color: var(--text-2);
    cursor: pointer;
  }
  .collapse:hover {
    border-color: var(--accent);
    color: var(--accent);
  }
  /* Collapsed sidebar → a thin vertical rail that reopens the filter panel. */
  .sidebar-rail {
    width: 40px;
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 10px;
    padding: 14px 0;
    background: var(--panel);
    border-right: 1px solid var(--border);
    color: var(--text-2);
    cursor: pointer;
    z-index: 10;
  }
  .sidebar-rail:hover {
    color: var(--accent);
  }
  .rail-icon {
    font-size: 16px;
    line-height: 1;
  }
  .rail-label {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    writing-mode: vertical-rl;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.04em;
  }
  .rail-badge {
    writing-mode: horizontal-tb;
    background: var(--accent);
    color: #fff;
    border-radius: 999px;
    padding: 0 6px;
    font-size: 11px;
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
