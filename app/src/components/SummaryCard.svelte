<script lang="ts">
  import { app } from '../lib/stores.svelte';

  // Counts come from each state's summary.json, carried in index.json.
  const counts = $derived<Record<string, number>>(app.activeState?.counts ?? {});

  const STATS: ReadonlyArray<{ key: string; label: string }> = [
    { key: 'parcel', label: 'Parcels' },
    { key: 'tower', label: 'Towers' },
    { key: 'solar_facility', label: 'Solar' },
    { key: 'distress_overlay', label: 'Distress tracts' },
  ];
</script>

{#if app.activeState}
  <section class="panel" data-testid="summary-card">
    <div class="grid">
      {#each STATS as s (s.key)}
        <div class="tile">
          <span class="num">{(counts[s.key] ?? 0).toLocaleString()}</span>
          <span class="lbl">{s.label}</span>
        </div>
      {/each}
    </div>
  </section>
{/if}

<style>
  .grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 8px;
  }
  .tile {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 9px 10px;
    text-align: center;
  }
  .num {
    display: block;
    font-size: 18px;
    font-weight: 600;
    letter-spacing: -0.02em;
    font-variant-numeric: tabular-nums;
  }
  .lbl {
    display: block;
    margin-top: 1px;
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
  }
</style>
