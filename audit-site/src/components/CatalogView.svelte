<script lang="ts">
  import { store } from '../lib/audit-store.svelte';
  import { buildCatalog } from '../lib/catalog';
  import CatalogGroup from './CatalogGroup.svelte';

  let { anchor = null }: { anchor?: string | null } = $props();

  // Built live from index.json (the auto-populate contract): a re-run reboots the
  // app and the catalog reflects the new data with no code change.
  const model = $derived(store.index ? buildCatalog(store.index) : null);

  const pointCount = $derived(model ? model.groups.reduce((n, g) => n + g.points.length, 0) : 0);

  // Deep-link from an Overview card: scroll the anchored group into view once the
  // model has rendered. rAF lets the DOM settle after App's scroll-to-top.
  $effect(() => {
    if (!anchor || !model) return;
    const id = anchor;
    requestAnimationFrame(() => {
      document.getElementById(id)?.scrollIntoView({ block: 'start' });
    });
  });
</script>

<div class="page">
  <div class="page-head">
    <h1>Data Catalog</h1>
    <p class="sub">
      Every data point we surface, grouped by what it tells you about a deal — with a plain trust
      rating, where it came from, and how current it is.
    </p>
  </div>

  {#if model}
    <p class="scope">
      {pointCount} data points · {model.groups.length} groups · AR / FL / MT / WV
    </p>
    {#each model.groups as group (group.def.id)}
      <CatalogGroup {group} />
    {/each}
  {/if}
</div>

<style>
  .scope {
    margin: 0 0 16px;
    font-size: 13px;
    color: var(--muted);
  }
</style>
