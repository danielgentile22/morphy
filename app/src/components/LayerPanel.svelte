<script lang="ts">
  import { app, BASE_COUNTY, BASE_PARCELS } from '../lib/stores.svelte';
  import { geojsonLayers, geojsonViews } from '../lib/catalog';
  import { layerColor, layerLabel, WONG } from '../lib/palette';

  const layers = $derived(app.catalog ? geojsonLayers(app.catalog) : []);
  const views = $derived(app.catalog ? geojsonViews(app.catalog) : []);

  // Names of heavy views currently lazy-loading their GeoJSON.
  const loading = $state(new Set<string>());

  async function toggle(name: string): Promise<void> {
    const willShow = !app.isLayerVisible(name);
    if (willShow && !app.layerData[name]) {
      loading.add(name);
      await app.ensureLayerLoaded(name);
      loading.delete(name);
      if (app.failedLayers.includes(name)) return; // load failed — stay off
    }
    app.setLayerVisible(name, willShow);
  }
</script>

{#snippet toggleRow(name: string, count: number)}
  {@const failed = app.failedLayers.includes(name)}
  {@const isLoading = loading.has(name)}
  <label class="toggle" class:disabled={failed}>
    <input
      type="checkbox"
      checked={app.isLayerVisible(name)}
      disabled={failed || isLoading}
      onchange={() => toggle(name)}
      data-testid="layer-toggle-{name}"
    />
    <span class="swatch" style:background={layerColor(name)}></span>
    <span class="name">{layerLabel(name)}</span>
    {#if failed}
      <span class="badge err">unavailable</span>
    {:else if isLoading}
      <span class="badge">loading…</span>
    {:else}
      <span class="count">{count.toLocaleString()}</span>
    {/if}
  </label>
{/snippet}

{#if app.catalog}
  {#if app.parcelsUrl || app.countyData}
    <section class="panel">
      <h2>Base layers</h2>
      {#if app.parcelsUrl}
        <label class="toggle">
          <input
            type="checkbox"
            checked={app.isLayerVisible(BASE_PARCELS)}
            onchange={() => app.setLayerVisible(BASE_PARCELS, !app.isLayerVisible(BASE_PARCELS))}
            data-testid="layer-toggle-parcels"
          />
          <span class="swatch" style:background={WONG.vermillion}></span>
          <span class="name">Parcels (vector tiles)</span>
        </label>
      {/if}
      {#if app.countyData}
        <label class="toggle">
          <input
            type="checkbox"
            checked={app.isLayerVisible(BASE_COUNTY)}
            onchange={() => app.setLayerVisible(BASE_COUNTY, !app.isLayerVisible(BASE_COUNTY))}
            data-testid="layer-toggle-county_boundaries"
          />
          <span class="swatch" style:background={WONG.orange}></span>
          <span class="name">County distress</span>
        </label>
      {/if}
    </section>
  {/if}
  <section class="panel">
    <h2>Layers</h2>
    {#each layers as l (l.name)}
      {@render toggleRow(l.name, l.rows)}
    {/each}
  </section>
  {#if views.length > 0}
    <section class="panel">
      <h2>Views</h2>
      <p class="hint">Derived outreach segments. Heavier ones load when switched on.</p>
      {#each views as v (v.name)}
        {@render toggleRow(v.name, v.rows)}
      {/each}
    </section>
  {/if}
{/if}

<style>
  .hint {
    margin: 0 0 6px;
    font-size: 11px;
    color: var(--muted);
  }
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
