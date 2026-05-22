<script lang="ts">
  import { onMount } from 'svelte';
  import { app } from './lib/stores.svelte';
  import MapView from './components/MapView.svelte';
  import StateSelector from './components/StateSelector.svelte';
  import SummaryCard from './components/SummaryCard.svelte';
  import LayerPanel from './components/LayerPanel.svelte';
  import Legend from './components/Legend.svelte';
  import SearchPanel from './components/SearchPanel.svelte';
  import FilterPanel from './components/FilterPanel.svelte';
  import TopList from './components/TopList.svelte';
  import DetailsPanel from './components/DetailsPanel.svelte';
  import { buildUrl } from './lib/url';

  // Captured synchronously, before any effect can rewrite the URL.
  const initialSearch = location.search;

  let showHelp = $state(false);

  function onKeydown(e: KeyboardEvent): void {
    if (e.key === 'Escape') {
      if (showHelp) showHelp = false;
      else app.clearSelection();
      return;
    }
    // Other shortcuts are inert while typing in a control.
    const el = e.target;
    if (
      el instanceof HTMLElement &&
      (el.tagName === 'INPUT' || el.tagName === 'SELECT' || el.isContentEditable)
    ) {
      return;
    }
    if (e.key === 'f') {
      e.preventDefault();
      document.querySelector<HTMLInputElement>('[data-testid="owner-search"]')?.focus();
    } else if (e.key === '?') {
      showHelp = !showHelp;
    }
  }

  onMount(() => {
    void app.boot(initialSearch);
    window.addEventListener('keydown', onKeydown);
    return () => window.removeEventListener('keydown', onKeydown);
  });

  // Keep the URL a shareable deep link — state, selected parcel, filters.
  // Gated on urlSyncReady so it cannot erase the deep-link before boot
  // has restored it.
  $effect(() => {
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
        <SearchPanel />
        <FilterPanel />
        <TopList />
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
      <MapView />
      <DetailsPanel />
      {#if app.status === 'loading'}
        <div class="loading-pill" data-testid="loading">Loading…</div>
      {/if}
    {/if}
  </main>

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
    background: var(--panel-2);
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
