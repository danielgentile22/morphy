<script lang="ts">
  // Settings → Filter defaults (PRD #121): snapshot the live Explore filters as
  // a personal default and auto-apply them when Explore opens. Reuses the real
  // shared FilterModel singleton, so a saved default can express anything the
  // filter panel can.
  import { userSettings } from '../lib/user-settings-store.svelte';
  import { filterModel } from '../lib/filter-model.svelte';
  import {
    serializeFilterModel,
    deserializeFilterModel,
    summarizeFilterModel,
  } from '../lib/filter-model';

  const s = $derived(userSettings.settings);
  // The human-readable summary of what's currently saved as the default.
  const savedSummary = $derived(
    s.filter_default ? summarizeFilterModel(deserializeFilterModel(s.filter_default)) : [],
  );
  // The summary of what's live in Explore right now (what "Save" would store).
  const liveSummary = $derived(summarizeFilterModel(filterModel.model));

  let status = $state<'idle' | 'saved' | 'cleared'>('idle');

  async function saveCurrent(): Promise<void> {
    const ok = await userSettings.saveFilterDefault(serializeFilterModel(filterModel.model), true);
    if (ok) status = 'saved';
  }
  async function clear(): Promise<void> {
    const ok = await userSettings.clearFilterDefault();
    if (ok) status = 'cleared';
  }
</script>

<section class="set-section" data-testid="settings-filters">
  <h2>Filter defaults</h2>
  <p class="hint">
    Save your current Explore filters so they apply automatically every session. A shared link with
    its own filters always wins.
  </p>

  <div class="set-group">
    <h3>Saved default</h3>
    {#if s.filter_default && savedSummary.length}
      <ul class="summary" data-testid="filter-default-summary">
        {#each savedSummary as line (line)}<li>{line}</li>{/each}
      </ul>
    {:else}
      <p class="hint" data-testid="filter-default-empty">No default saved — Explore opens unfiltered.</p>
    {/if}

    <label class="set-check">
      <input
        type="checkbox"
        data-testid="filter-default-apply"
        checked={s.filter_default_apply}
        disabled={!s.filter_default}
        onchange={(e) => userSettings.save({ filter_default_apply: e.currentTarget.checked })}
      />
      Apply my default filters when Explore opens
    </label>
  </div>

  <div class="set-group">
    <h3>Current Explore filters</h3>
    {#if liveSummary.length}
      <ul class="summary" data-testid="filter-live-summary">
        {#each liveSummary as line (line)}<li>{line}</li>{/each}
      </ul>
    {:else}
      <p class="hint">No filters are currently active in Explore.</p>
    {/if}
    <div class="set-row">
      <button
        class="set-btn"
        data-testid="filter-default-save"
        disabled={!liveSummary.length}
        onclick={saveCurrent}
      >
        Save current as my default
      </button>
      <button
        class="set-btn secondary"
        data-testid="filter-default-clear"
        disabled={!s.filter_default}
        onclick={clear}
      >
        Clear default
      </button>
      {#if status === 'saved'}<span class="set-status ok">Saved ✓</span>{/if}
      {#if status === 'cleared'}<span class="set-status ok">Cleared ✓</span>{/if}
    </div>
  </div>
</section>

<style>
  .summary {
    margin: 0 0 12px;
    padding-left: 18px;
    font-size: 12.5px;
    color: var(--text-2);
  }
  .summary li {
    margin: 2px 0;
  }
</style>
