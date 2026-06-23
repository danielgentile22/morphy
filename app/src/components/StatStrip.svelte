<script lang="ts">
  // Compact two-tile stat strip (UI overhaul #119), replacing the old 2×2
  // summary grid. Only the numbers a triager acts on:
  //   • Towers — LIVE: the count of towers matching the active filters, read
  //     from the SAME shared derivation the map's tower layer and the ranked
  //     candidates list use (so the three can never disagree).
  //   • Solar — STATIC: the all-states solar-facility total. Solar can't be
  //     cluster-filtered today (owner-name string only, no cluster id), so the
  //     tile shows coverage, not a live match.
  import { exploreTowers } from '../lib/explore-towers.svelte';
  import { app } from '../lib/stores.svelte';

  const towers = $derived(exploreTowers.count);
  const solar = $derived(app.solarCount);

  function fmt(n: number): string {
    return n.toLocaleString();
  }
</script>

<div class="stat-strip" data-testid="stat-strip">
  <div class="stat-tile stat-sm" data-tone="info" data-testid="stat-towers">
    <span class="stat-eyebrow">Towers</span>
    <span class="stat-value">{fmt(towers)}</span>
  </div>
  <div class="stat-tile stat-sm" data-tone="warning" data-testid="stat-solar">
    <span class="stat-eyebrow">Solar</span>
    <span class="stat-value">{fmt(solar)}</span>
  </div>
</div>

<style>
  .stat-strip {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
    padding: 12px 16px;
  }
</style>
