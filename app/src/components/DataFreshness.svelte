<script lang="ts">
  // Data freshness read-out (#235) — read-only view of the deploy-time
  // freshness snapshot, so the user can answer "how current is this
  // data?" without asking the operator. A missing snapshot degrades to a
  // quiet placeholder, never an error.
  import { onMount } from 'svelte';
  import { loadFreshness, freshnessRows, fmtDate, type FreshnessRow } from '../lib/data-freshness';

  let rows = $state<FreshnessRow[] | null>(null);
  let snapshotDate = $state<string | null>(null);
  let loading = $state(true);

  onMount(async () => {
    const doc = await loadFreshness();
    if (doc) {
      rows = freshnessRows(doc, new Date());
      snapshotDate = fmtDate(doc.generated_at);
    }
    loading = false;
  });
</script>

<div class="freshness" data-testid="data-freshness">
  {#if loading}
    <p class="muted">Loading…</p>
  {:else if !rows || rows.length === 0}
    <p class="muted" data-testid="freshness-unavailable">Freshness snapshot isn't available.</p>
  {:else}
    <table class="t" data-testid="freshness-table">
      <tbody>
        {#each rows as r (r.label)}
          <tr>
            <td>{r.label}</td>
            <td class="when">{r.refreshed ?? '—'}</td>
            <td class="ago">{r.ago}</td>
          </tr>
        {/each}
      </tbody>
    </table>
    <p class="foot">
      Snapshot from the last deploy{#if snapshotDate}&nbsp;({snapshotDate}){/if}. Derived layers
      (owner clustering, scoring, tower-parcel join) rebuild with every deploy.
    </p>
  {/if}
</div>

<style>
  .muted {
    color: var(--muted);
    font-size: 13px;
  }
  .t {
    width: 100%;
    max-width: 640px;
    border-collapse: collapse;
    font-size: 13px;
  }
  .t td {
    padding: 4px 6px;
    border-bottom: 1px solid var(--border);
  }
  .when {
    text-align: right;
    font-variant-numeric: tabular-nums;
    font-weight: 600;
    white-space: nowrap;
  }
  .ago {
    text-align: right;
    color: var(--muted);
    font-size: 11.5px;
    white-space: nowrap;
    width: 110px;
  }
  .foot {
    margin-top: 10px;
    color: var(--muted);
    font-size: 11.5px;
  }
</style>
