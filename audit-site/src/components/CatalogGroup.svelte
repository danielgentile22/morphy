<script lang="ts">
  import { slide } from 'svelte/transition';
  import type { CatalogGroup } from '../lib/catalog';
  import DataPointRow from './DataPointRow.svelte';

  let { group }: { group: CatalogGroup } = $props();

  // Each section collapses independently. Defaults open so nothing is hidden on
  // load; per-instance, so a re-run (which remounts the app) resets to open.
  let open = $state(true);
  const rowsId = $derived(`catalog-rows-${group.def.id}`);
</script>

<!-- id = the deep-link anchor (`#/catalog/<id>`), used by the Overview cards. -->
<section class="group panel" id={group.def.id}>
  <!-- Disclosure button inside the heading: keeps the h2 for screen-reader
       navigation while exposing the expand/collapse state. -->
  <h2 class="head">
    <button
      type="button"
      class="head-btn"
      class:open
      aria-expanded={open}
      aria-controls={rowsId}
      onclick={() => (open = !open)}
    >
      <span class="chev" class:open aria-hidden="true">▸</span>
      <span class="emoji" aria-hidden="true">{group.def.emoji}</span>
      <span class="titles">
        <span class="title">{group.def.title}</span>
        <span class="blurb">{group.def.blurb}</span>
      </span>
      <span class="count">{group.points.length}</span>
    </button>
  </h2>
  {#if open}
    <div class="rows" id={rowsId} transition:slide={{ duration: 170 }}>
      {#each group.points as point (point.baseId)}
        <DataPointRow {point} />
      {/each}
    </div>
  {/if}
</section>

<style>
  .group {
    margin-bottom: 16px;
    overflow: hidden;
    scroll-margin-top: calc(var(--nav-h) + 12px);
  }
  /* h2 reset — the visible heading size comes from .title below. */
  .head {
    margin: 0;
    font-size: inherit;
    font-weight: inherit;
  }
  .head-btn {
    display: flex;
    align-items: center;
    gap: 12px;
    width: 100%;
    padding: 13px 14px;
    background: var(--panel-2);
    border: none;
    border-bottom: 1px solid transparent;
    color: var(--text);
    text-align: left;
    font: inherit;
    cursor: pointer;
    transition: background 0.12s ease;
  }
  .head-btn.open {
    border-bottom-color: var(--border);
  }
  .head-btn:hover {
    background: color-mix(in srgb, var(--panel-2) 90%, var(--text));
  }
  .head-btn:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: -2px;
  }
  .chev {
    flex-shrink: 0;
    font-size: 11px;
    color: var(--muted);
    transition: transform 0.15s ease;
  }
  .chev.open {
    transform: rotate(90deg);
  }
  .emoji {
    font-size: 20px;
    line-height: 1;
    flex-shrink: 0;
  }
  .titles {
    min-width: 0;
    flex: 1 1 auto;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .title {
    font-size: 15px;
    font-weight: 600;
  }
  .blurb {
    font-size: 12.5px;
    font-weight: 400;
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
