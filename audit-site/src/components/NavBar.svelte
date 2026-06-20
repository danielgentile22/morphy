<script lang="ts">
  import { router, hrefs } from '../lib/router.svelte';
  import { themeStore } from '../lib/theme.svelte';

  const route = $derived(router.route);

  interface NavItem {
    label: string;
    href: string;
    active: boolean;
  }

  // Primary nav reframed around what the co-founder uses (PRD #178 / #184): the
  // catalog is the front door; the technical audit surfaces (Signals, Cards,
  // Verification, Reconciliation, Methodology) move to the Full-audit footer.
  const items = $derived<NavItem[]>([
    { label: 'Overview', href: hrefs.overview, active: route.name === 'overview' },
    { label: 'Data Catalog', href: hrefs.catalog(), active: route.name === 'catalog' },
    { label: 'What needs updating', href: hrefs.freshness, active: route.name === 'freshness' },
  ]);
</script>

<header class="nav">
  <a class="brand" href={hrefs.overview}>
    <span class="brand-mark" aria-hidden="true">◆</span>
    <span class="brand-text">Data Catalog</span>
  </a>
  <nav class="links" aria-label="Sections">
    {#each items as it (it.label)}
      <a href={it.href} class="link" class:active={it.active} aria-current={it.active ? 'page' : undefined}>
        {it.label}
      </a>
    {/each}
  </nav>
  <button class="theme" onclick={() => themeStore.toggle()} title="Toggle light / dark" aria-label="Toggle theme">
    {themeStore.current === 'dark' ? '☀' : '☾'}
  </button>
</header>

<style>
  .nav {
    position: sticky;
    top: 0;
    z-index: 50;
    height: var(--nav-h);
    display: flex;
    align-items: center;
    gap: 18px;
    padding: 0 18px;
    background: color-mix(in srgb, var(--panel) 88%, transparent);
    backdrop-filter: saturate(1.4) blur(8px);
    border-bottom: 1px solid var(--border);
  }
  .brand {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    font-weight: 700;
    letter-spacing: -0.02em;
    color: var(--text);
    flex-shrink: 0;
  }
  .brand:hover {
    text-decoration: none;
  }
  .brand-mark {
    color: var(--accent);
    font-size: 13px;
  }
  .links {
    display: flex;
    align-items: center;
    gap: 2px;
    /* One row that scrolls horizontally when it overflows (mobile) instead of
       wrapping into the fixed-height bar — keeps Overview/Signals reachable. */
    flex: 1 1 auto;
    min-width: 0;
    flex-wrap: nowrap;
    overflow-x: auto;
    scrollbar-width: none;
  }
  .links::-webkit-scrollbar {
    display: none;
  }
  .link {
    padding: 6px 11px;
    border-radius: var(--radius-sm);
    color: var(--text-2);
    font-weight: 500;
    font-size: 13.5px;
    white-space: nowrap;
    flex-shrink: 0;
  }
  .link:hover {
    background: var(--panel-2);
    text-decoration: none;
    color: var(--text);
  }
  .link.active {
    background: var(--accent-bg);
    color: var(--accent);
    font-weight: 600;
  }
  .theme {
    margin-left: auto;
    flex-shrink: 0;
    width: 32px;
    height: 32px;
    border: 1px solid var(--border);
    background: var(--panel);
    color: var(--text-2);
    border-radius: var(--radius-sm);
    font-size: 15px;
    line-height: 1;
  }
  .theme:hover {
    background: var(--panel-2);
  }
</style>
