<script lang="ts">
  import { app } from '../lib/stores.svelte';
  import { geojsonLayers } from '../lib/catalog';
  import { HIDDEN_LAYERS } from '../lib/stores-helpers';
  import { layerColor, layerLabel } from '../lib/palette';

  // The map renders towers + solar as toggleable overlays, on top of the
  // always-on parcel base tiles (which fade in on zoom and are no longer a
  // setting). Distress became a filter field, and the derived-view overlays,
  // the county choropleth, and the legend were all retired (UI overhaul
  // round 3) — all narrowing now happens in the top filter bar.
  const layers = $derived(
    app.catalog ? geojsonLayers(app.catalog).filter((l) => !HIDDEN_LAYERS.has(l.name)) : [],
  );

  function toggle(name: string): void {
    app.setLayerVisible(name, !app.isLayerVisible(name));
  }
</script>

{#if layers.length > 0}
  <section class="panel">
    <h2>Layers</h2>
    {#each layers as l (l.name)}
      {@const failed = app.failedLayers.includes(l.name)}
      <label class="toggle" class:disabled={failed}>
        <input
          type="checkbox"
          checked={app.isLayerVisible(l.name)}
          disabled={failed}
          onchange={() => toggle(l.name)}
          data-testid="layer-toggle-{l.name}"
        />
        <span class="swatch" style:background={layerColor(l.name)}></span>
        <span class="name">{layerLabel(l.name)}</span>
        {#if failed}
          <span class="badge err">unavailable</span>
        {:else}
          <span class="count">{l.rows.toLocaleString()}</span>
        {/if}
      </label>
    {/each}
  </section>
{/if}

<style>
  .toggle {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 5px 0;
    font-size: 13px;
    cursor: pointer;
  }
  .toggle.disabled {
    cursor: not-allowed;
    color: var(--muted);
  }
  .toggle input {
    margin: 0;
    flex-shrink: 0;
  }
  .swatch {
    width: 13px;
    height: 13px;
    border-radius: 3px;
    border: 1px solid rgba(0, 0, 0, 0.15);
    flex-shrink: 0;
  }
  .name {
    flex: 1;
    min-width: 0;
  }
  .count {
    font-size: 11px;
    color: var(--muted);
    font-variant-numeric: tabular-nums;
  }
  .badge {
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--muted);
  }
  .badge.err {
    color: var(--danger);
  }
</style>
