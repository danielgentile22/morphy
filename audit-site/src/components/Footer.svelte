<script lang="ts">
  import { router, hrefs, type Route } from '../lib/router.svelte';

  const route = $derived(router.route);

  const docActive = (r: Route, file: string) => r.name === 'doc' && r.file === file;

  // The technical audit surfaces, demoted from the primary nav (PRD #178 / #184).
  // Every route still works — they're one click away, just no longer the default.
  const items = $derived([
    { label: 'Signals', href: hrefs.signals(), active: route.name === 'signals' || route.name === 'signal' },
    { label: 'Cards', href: hrefs.cards, active: route.name === 'cards' || route.name === 'card' },
    { label: 'Verification', href: hrefs.doc('verification-log.md'), active: docActive(route, 'verification-log.md') },
    { label: 'Reconciliation', href: hrefs.doc('INDEX.md'), active: docActive(route, 'INDEX.md') },
    { label: 'Methodology', href: hrefs.doc('PLAN.md'), active: docActive(route, 'PLAN.md') },
  ]);
</script>

<footer class="full-audit" aria-label="Full audit">
  <span class="label">Full audit</span>
  <nav class="links" aria-label="Full audit surfaces">
    {#each items as it (it.label)}
      <a href={it.href} class="link" class:active={it.active} aria-current={it.active ? 'page' : undefined}>
        {it.label}
      </a>
    {/each}
  </nav>
  <span class="note">The evidence behind the catalog — provenance, verification, and methodology.</span>
</footer>

<style>
  .full-audit {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px 14px;
    max-width: 1200px;
    margin: 40px auto 0;
    padding: 16px 18px 28px;
    border-top: 1px solid var(--border);
  }
  .label {
    font-size: 10.5px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--muted);
    flex-shrink: 0;
  }
  .links {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 2px;
  }
  .link {
    padding: 4px 9px;
    border-radius: var(--radius-sm);
    color: var(--text-2);
    font-weight: 500;
    font-size: 12.5px;
    white-space: nowrap;
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
  .note {
    flex: 1 1 220px;
    min-width: 0;
    text-align: right;
    font-size: 11.5px;
    color: var(--muted);
  }
  @media (max-width: 620px) {
    .note {
      flex-basis: 100%;
      text-align: left;
    }
  }
</style>
