<script lang="ts">
  import type { CatalogGroup } from '../lib/catalog';
  import DataPointRow from './DataPointRow.svelte';

  let { group }: { group: CatalogGroup } = $props();
</script>

<!-- id = the deep-link anchor (`#/catalog/<id>`), used by the Overview cards. -->
<section class="group panel" id={group.def.id}>
  <header class="head">
    <span class="emoji" aria-hidden="true">{group.def.emoji}</span>
    <div class="titles">
      <h2>{group.def.title}</h2>
      <p class="blurb">{group.def.blurb}</p>
    </div>
    <span class="count">{group.points.length}</span>
  </header>
  <div class="rows">
    {#each group.points as point (point.baseId)}
      <DataPointRow {point} />
    {/each}
  </div>
</section>

<style>
  .group {
    margin-bottom: 16px;
    overflow: hidden;
    scroll-margin-top: calc(var(--nav-h) + 12px);
  }
  .head {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 13px 14px;
    border-bottom: 1px solid var(--border);
    background: var(--panel-2);
  }
  .emoji {
    font-size: 20px;
    line-height: 1;
    flex-shrink: 0;
  }
  .titles {
    min-width: 0;
    flex: 1 1 auto;
  }
  .titles h2 {
    font-size: 15px;
    margin: 0;
  }
  .blurb {
    margin: 2px 0 0;
    font-size: 12.5px;
    color: var(--muted);
  }
  .count {
    flex-shrink: 0;
    font-size: 12px;
    font-weight: 600;
    color: var(--text-2);
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 100px;
    padding: 1px 9px;
  }
</style>
