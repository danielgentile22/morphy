<script lang="ts">
  import type { DataPoint } from '../lib/catalog';
  import { trustBadge, whereFrom, howCurrent } from '../lib/catalog-language';
  import { STATE_NAMES } from '../lib/signals';

  let { point }: { point: DataPoint } = $props();

  const badge = $derived(trustBadge(point.confidence));
  // Recognised points lead with the plain meaning; a newly-added one has no
  // curated meaning yet, so it shows its raw audit verdict instead (never hidden).
  const lead = $derived(point.meaning ?? point.verdict);

  // The collapsed per-state strip is a richer drill-in in a later slice; here we
  // just name the states a per-state row stands in for, in fips order.
  const stateAbbr: Record<string, string> = { '05': 'AR', '12': 'FL', '30': 'MT', '54': 'WV' };
</script>

<div class="row">
  <span class="trust chip chip--{badge.tone}" title="Trust: {point.confidence}">{badge.label}</span>
  <div class="body">
    <p class="lead" class:raw={!point.meaning}>{lead}</p>
    <div class="meta">
      <span class="base">{point.baseId}</span>
      <span class="dot" aria-hidden="true">·</span>
      <span title="Where the data comes from">{whereFrom(point.tags.upstream_origin)}</span>
      <span class="dot" aria-hidden="true">·</span>
      <span title="How current the data is">{howCurrent(point.tags.freshness_risk)}</span>
      {#if point.isPerState}
        <span class="dot" aria-hidden="true">·</span>
        <span class="states" title="One row standing in for four per-state copies">
          {point.states.map((c) => stateAbbr[c.fips] ?? STATE_NAMES[c.fips] ?? c.fips).join(' / ')}
        </span>
      {/if}
    </div>
  </div>
</div>

<style>
  .row {
    display: grid;
    grid-template-columns: 74px 1fr;
    gap: 12px;
    align-items: start;
    padding: 11px 14px;
    border-top: 1px solid var(--border);
  }
  .row:first-child {
    border-top: none;
  }
  .trust {
    justify-content: center;
    margin-top: 1px;
  }
  .body {
    min-width: 0;
  }
  .lead {
    margin: 0;
    font-size: 13.5px;
    color: var(--text);
    line-height: 1.5;
  }
  .lead.raw {
    color: var(--text-2);
  }
  .meta {
    margin-top: 4px;
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: 6px;
    font-size: 12px;
    color: var(--muted);
  }
  .base {
    font-family: var(--mono);
    font-size: 11.5px;
    color: var(--text-2);
  }
  .states {
    color: var(--text-2);
    font-weight: 500;
  }
  .dot {
    color: var(--border-strong);
  }
</style>
