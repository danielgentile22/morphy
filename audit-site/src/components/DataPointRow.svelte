<script lang="ts">
  import { type DataPoint, stateStrip } from '../lib/catalog';
  import { trustBadge, whereFrom, howCurrent } from '../lib/catalog-language';
  import { hrefs } from '../lib/router.svelte';

  let { point }: { point: DataPoint } = $props();

  const badge = $derived(trustBadge(point.confidence));
  // Recognised points lead with the plain meaning; a newly-added one has no
  // curated meaning yet, so it shows its raw audit verdict instead (never hidden).
  const lead = $derived(point.meaning ?? point.verdict);

  // Per-state rows get a 4-cell AR/FL/MT/WV trust strip; national rows get `[]`
  // (no strip). Each cell's trust comes straight from index.json (auto-populate).
  const strip = $derived(stateStrip(point));
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
    </div>
    {#if strip.length}
      <!-- One cell per state, colored by that state's trust; click → its evidence. -->
      <div class="strip" role="group" aria-label="Per-state trust — click a state for its evidence">
        {#each strip as col (col.fips)}
          {#if col.cell}
            {@const b = trustBadge(col.cell.confidence)}
            <a
              class="cell chip chip--{b.tone}"
              href={hrefs.signal(col.cell.signal.id)}
              title="{col.name}: {b.label} trust — open evidence"
            >
              <span class="abbr">{col.abbr}</span>
            </a>
          {:else}
            <span class="cell cell--empty chip chip--muted" title="{col.name}: no data">
              <span class="abbr">{col.abbr}</span>
            </span>
          {/if}
        {/each}
      </div>
    {/if}
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
  .dot {
    color: var(--border-strong);
  }
  .strip {
    margin-top: 8px;
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
  }
  .cell {
    min-width: 36px;
    justify-content: center;
    font-size: 11px;
    letter-spacing: 0.02em;
  }
  .abbr {
    font-family: var(--mono);
  }
  a.cell {
    transition: filter 0.1s ease;
  }
  a.cell:hover {
    text-decoration: none;
    filter: brightness(1.06) saturate(1.1);
  }
  .cell--empty {
    opacity: 0.6;
  }
</style>
