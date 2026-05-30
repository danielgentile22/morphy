<script lang="ts">
  import { app } from '../lib/stores.svelte';

  function onChange(e: Event): void {
    const fips = (e.currentTarget as HTMLSelectElement).value;
    if (fips && fips !== app.activeFips) {
      // Picking a state frames the map on it (and loads its parcels/catalog);
      // the all-anchors tower layer stays put underneath.
      void app.focusState(fips);
    }
  }
</script>

{#if app.index && app.index.states.length > 0}
  <div class="state-selector">
    <label for="state-select">State</label>
    <select
      id="state-select"
      value={app.activeFips ?? ''}
      onchange={onChange}
      disabled={app.status === 'loading'}
      data-testid="state-select"
    >
      {#each app.index.states as s (s.fips)}
        <option value={s.fips}>{s.abbr} — {s.name}</option>
      {/each}
    </select>
  </div>
{/if}

<style>
  .state-selector {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  label {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--muted);
  }
  select {
    appearance: none;
    width: 100%;
    padding: 8px 10px;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--bg);
    color: var(--text);
    font-size: 14px;
    font-family: inherit;
  }
  select:disabled {
    opacity: 0.6;
  }
</style>
