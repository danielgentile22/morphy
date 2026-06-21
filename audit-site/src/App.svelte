<script lang="ts">
  import { onMount } from 'svelte';
  import { store } from './lib/audit-store.svelte';
  import { router } from './lib/router.svelte';
  import { themeStore } from './lib/theme.svelte';
  import NavBar from './components/NavBar.svelte';
  import Footer from './components/Footer.svelte';
  import Overview from './components/Overview.svelte';
  import CatalogView from './components/CatalogView.svelte';
  import FreshnessView from './components/FreshnessView.svelte';
  import SignalsBrowser from './components/SignalsBrowser.svelte';
  import SignalDetail from './components/SignalDetail.svelte';
  import CardsBrowser from './components/CardsBrowser.svelte';
  import CardDetail from './components/CardDetail.svelte';
  import DocView from './components/DocView.svelte';
  import AskClaude from './components/AskClaude.svelte';
  import { enableTextSelectionInLinks } from './lib/selectable-links';

  themeStore.init();
  onMount(() => {
    void store.load();
    // Let text inside clickable cards be drag-selected (so "highlight → Ask
    // Claude" works on the card-heavy catalog, not just on plain prose).
    return enableTextSelectionInLinks();
  });

  const route = $derived(router.route);

  // Scroll to top on navigation, except doc views (they manage their own
  // anchor scroll so a signal→dossier deep-link lands on the right heading).
  $effect(() => {
    if (route.name !== 'doc') window.scrollTo({ top: 0 });
  });
</script>

<NavBar />

<main>
  {#if store.loading}
    <div class="state">
      <div class="spinner" aria-hidden="true"></div>
      <p>Loading the audit…</p>
    </div>
  {:else if store.error}
    <div class="state state--err">
      <h2>Couldn't load the audit data</h2>
      <p class="muted">{store.error}</p>
      <p class="muted">
        In dev, the artifacts are served from <code>docs/research/data-audit/</code> by the
        Vite plugin — make sure you're running <code>npm run dev</code> in <code>audit-site/</code>.
      </p>
      <button onclick={() => store.load()}>Retry</button>
    </div>
  {:else if route.name === 'overview'}
    <Overview />
  {:else if route.name === 'catalog'}
    <CatalogView anchor={route.anchor} />
  {:else if route.name === 'freshness'}
    <FreshnessView />
  {:else if route.name === 'signals'}
    <SignalsBrowser query={route.query} />
  {:else if route.name === 'signal'}
    <SignalDetail id={route.id} />
  {:else if route.name === 'cards'}
    <CardsBrowser />
  {:else if route.name === 'card'}
    <CardDetail id={route.id} />
  {:else if route.name === 'doc'}
    <DocView file={route.file} anchor={route.anchor} />
  {/if}
</main>

<Footer />

<!-- Mounted globally (PRD #188): the corner button + panel are available on
     every view, independent of which route or whether the audit data loaded. -->
<AskClaude />

<style>
  .state {
    max-width: 560px;
    margin: 80px auto;
    text-align: center;
    padding: 0 24px;
  }
  .state--err {
    text-align: left;
  }
  .state button {
    margin-top: 14px;
    padding: 8px 16px;
    border: 1px solid var(--border-strong);
    background: var(--panel);
    color: var(--text);
    border-radius: var(--radius-sm);
    font-weight: 600;
  }
  .state code {
    background: var(--panel-2);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 1px 5px;
    font-family: var(--mono);
    font-size: 0.86em;
  }
  .spinner {
    width: 26px;
    height: 26px;
    margin: 0 auto 14px;
    border: 3px solid var(--border);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }
  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
</style>
