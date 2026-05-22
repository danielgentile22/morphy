<script lang="ts">
  import { app, BASE_COUNTY, BASE_PARCELS } from '../lib/stores.svelte';
  import {
    DISTRESS_TIERS,
    distressTierColor,
    distressTierLabel,
    layerColor,
    layerLabel,
    overlayTypeColor,
    overlayTypeLabel,
  } from '../lib/palette';

  // Regenerated from whatever layers are currently visible.
  const visible = $derived(
    Object.entries(app.layerVisible)
      .filter(([, on]) => on)
      .map(([name]) => name),
  );
  // Parcels + the choropleth are both shaded by distress tier.
  const showTierScale = $derived(
    visible.includes(BASE_PARCELS) || visible.includes(BASE_COUNTY),
  );
  const catalogVisible = $derived(
    visible.filter((n) => n !== BASE_PARCELS && n !== BASE_COUNTY),
  );
</script>

{#if visible.length > 0}
  <section class="panel" data-testid="legend">
    <h2>Legend</h2>
    <div class="items">
      {#if showTierScale}
        <div class="group">Distress tier — counties &amp; parcels</div>
        {#each DISTRESS_TIERS as tier (tier)}
          <div class="item">
            <span class="sw" style:background={distressTierColor(tier)}></span>
            {distressTierLabel(tier)}
          </div>
        {/each}
      {/if}
      {#each catalogVisible as name (name)}
        {#if name === 'distress_overlays'}
          <div class="item">
            <span class="sw" style:background={overlayTypeColor('opportunity_zone')}></span>
            {overlayTypeLabel('opportunity_zone')}
          </div>
          <div class="item">
            <span class="sw" style:background={overlayTypeColor('qct')}></span>
            {overlayTypeLabel('qct')}
          </div>
        {:else}
          <div class="item">
            <span class="sw" style:background={layerColor(name)}></span>
            {layerLabel(name)}
          </div>
        {/if}
      {/each}
    </div>
  </section>
{/if}

<style>
  h2 {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 6px;
  }
  .items {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .group {
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: var(--muted);
    margin-top: 2px;
  }
  .item {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12px;
  }
  .sw {
    width: 13px;
    height: 13px;
    border-radius: 3px;
    border: 1px solid rgba(0, 0, 0, 0.15);
    flex-shrink: 0;
  }
</style>
