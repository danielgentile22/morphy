<script lang="ts">
  import { hrefs } from '../lib/router.svelte';

  // Graceful placeholder until the live freshness slice (#185) wires up
  // freshness.json + the client model + the per-source table. Shipping the tab
  // now (PRD #178 Phase 1) means the nav is complete and never points at a 404.
</script>

<div class="page">
  <div class="page-head">
    <h1>What needs updating</h1>
    <p class="sub">
      A living view of each source — when it was last pulled and whether it's due or overdue —
      so the data keeps earning its keep over time.
    </p>
  </div>

  <section class="placeholder" aria-label="Freshness data not yet generated">
    <span class="icon" aria-hidden="true">⏳</span>
    <h2>Freshness data not yet generated</h2>
    <p>
      The last-pulled dates and due/overdue status for each source aren't available yet. This view
      goes live once the freshness snapshot is baked into the next deploy.
    </p>
    <p class="meanwhile">
      In the meantime, the <a href={hrefs.overview}>Overview</a> flags anything that looks likely to
      be stale based on each source's freshness risk, and the
      <a href={hrefs.catalog()}>Data Catalog</a> shows how current each data point is.
    </p>
  </section>
</div>

<style>
  .placeholder {
    max-width: 560px;
    margin: 8px auto 0;
    text-align: center;
    padding: 40px 28px;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    box-shadow: var(--shadow);
  }
  .icon {
    font-size: 34px;
    line-height: 1;
    display: block;
    margin-bottom: 12px;
  }
  .placeholder h2 {
    font-size: 16px;
    margin: 0 0 8px;
  }
  .placeholder p {
    margin: 0;
    font-size: 13.5px;
    line-height: 1.55;
    color: var(--text-2);
  }
  .meanwhile {
    margin-top: 14px;
    font-size: 12.5px;
    color: var(--muted);
  }
</style>
