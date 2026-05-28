<script lang="ts">
  import { app } from '../lib/stores.svelte';
  import { facetValues, facetRange } from '../lib/facets';
  import { distressTierLabel, ownerKindLabel } from '../lib/palette';
  import { fmtInt } from '../lib/format';
  import type { FilterState } from '../lib/filters';

  const facets = $derived(app.facets);

  // county_fips -> county name, for friendly county filter labels.
  const countyNames = $derived.by(() => {
    const map = new Map<string, string>();
    for (const f of app.countyData?.features ?? []) {
      const p = (f.properties ?? {}) as Record<string, unknown>;
      if (typeof p.county_fips === 'string') {
        map.set(p.county_fips, typeof p.county_name === 'string' ? p.county_name : p.county_fips);
      }
    }
    return map;
  });

  function toggleValue(list: string[], value: string): string[] {
    return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
  }

  function rangeOrNull(
    column: 'assessed_value' | 'acreage',
    lo: number,
    hi: number,
  ): [number, number] | null {
    const r = facetRange(facets!, column);
    // A pair equal to the facet's full extent means "no constraint".
    if (r && lo <= r.min && hi >= r.max) return null;
    return [lo, hi];
  }
</script>

{#snippet chipGroup(
  title: string,
  column: string,
  selected: string[],
  label: (v: string) => string,
  patch: (next: string[]) => Partial<FilterState>,
)}
  {#if facets && facetValues(facets, column).length > 0}
    <div class="group">
      <span class="glabel">{title}</span>
      <div class="chips">
        {#each facetValues(facets, column) as fv (fv.value)}
          <button
            type="button"
            class="chip"
            class:on={selected.includes(fv.value)}
            onclick={() => app.updateFilter(patch(toggleValue(selected, fv.value)))}
          >
            {label(fv.value)}
            <span class="ct">{fmtInt(fv.count)}</span>
          </button>
        {/each}
      </div>
    </div>
  {/if}
{/snippet}

{#snippet check(label: string, value: boolean, set: (v: boolean) => void)}
  <label class="check">
    <input type="checkbox" checked={value} onchange={(e) => set(e.currentTarget.checked)} />
    <span>{label}</span>
  </label>
{/snippet}

{#snippet checklist(
  title: string,
  column: string,
  selected: string[],
  label: (v: string) => string,
  patch: (next: string[]) => Partial<FilterState>,
)}
  {#if facets && facetValues(facets, column).length > 0}
    <details class="group">
      <summary>{title}{selected.length ? ` · ${selected.length} selected` : ''}</summary>
      <div class="checklist">
        {#each facetValues(facets, column) as fv (fv.value)}
          <label class="check">
            <input
              type="checkbox"
              checked={selected.includes(fv.value)}
              onchange={() => app.updateFilter(patch(toggleValue(selected, fv.value)))}
            />
            <span class="cl-name">{label(fv.value)}</span>
            <span class="ct">{fmtInt(fv.count)}</span>
          </label>
        {/each}
      </div>
    </details>
  {/if}
{/snippet}

{#if app.filtersAvailable && facets}
  <section class="panel" data-testid="filter-panel">
    <header class="fheader">
      <h2>Filters</h2>
      <button
        type="button"
        class="reset"
        disabled={!app.filtersActive}
        onclick={() => app.resetFilters()}
        data-testid="reset-filters"
      >
        Reset all
      </button>
    </header>

    <div
      class="count"
      class:active={app.filtersActive}
      class:err={app.filterStatus === 'error'}
      data-testid="filter-count"
    >
      {#if app.filterStatus === 'error'}
        Filter query failed
      {:else if app.filterStatus === 'querying'}
        Counting…
      {:else if app.filtersActive && app.filterCount !== null}
        {fmtInt(app.filterCount)} parcels match
      {:else}
        {fmtInt(facets.total)} parcels (no filter)
      {/if}
    </div>

    {@render chipGroup('Owner type', 'owner_kind', app.filters.ownerKind, ownerKindLabel, (v) => ({
      ownerKind: v,
    }))}
    {@render chipGroup(
      'Distress tier',
      'distress_tier',
      app.filters.distressTier,
      distressTierLabel,
      (v) => ({ distressTier: v }),
    )}

    <div class="group">
      <span class="glabel">Hosts infrastructure</span>
      <div class="checks">
        {@render check('Tower', app.filters.hasTower, (v) => app.updateFilter({ hasTower: v }))}
        {@render check('Solar', app.filters.hasSolar, (v) => app.updateFilter({ hasSolar: v }))}
        {@render check('Billboard', app.filters.hasBillboard, (v) =>
          app.updateFilter({ hasBillboard: v }),
        )}
      </div>
    </div>

    <div class="group">
      <span class="glabel">Distress flags</span>
      <div class="checks">
        {@render check('Opportunity Zone', app.filters.inOz, (v) => app.updateFilter({ inOz: v }))}
        {@render check('Qualified Census Tract', app.filters.inQct, (v) =>
          app.updateFilter({ inQct: v }),
        )}
        {@render check('Persistent poverty', app.filters.persistentPoverty, (v) =>
          app.updateFilter({ persistentPoverty: v }),
        )}
      </div>
    </div>

    <div class="group">
      <span class="glabel">
        Min. interestingness score: {app.filters.scoreMin.toFixed(2)}
      </span>
      <input
        type="range"
        min="0"
        max="1"
        step="0.05"
        value={app.filters.scoreMin}
        oninput={(e) => app.updateFilter({ scoreMin: Number(e.currentTarget.value) })}
        data-testid="score-slider"
      />
    </div>

    {#if facetRange(facets, 'owner_cluster_size')}
      {@const cr = facetRange(facets, 'owner_cluster_size')!}
      <div class="group">
        <span class="glabel">Min. parcels owned: {app.filters.clusterSizeMin}</span>
        <input
          type="range"
          min="1"
          max={Math.min(cr.max, 500)}
          step="1"
          value={app.filters.clusterSizeMin}
          oninput={(e) => app.updateFilter({ clusterSizeMin: Number(e.currentTarget.value) })}
        />
      </div>
    {/if}

    {#if facetRange(facets, 'assessed_value')}
      {@const ar = facetRange(facets, 'assessed_value')!}
      <div class="group">
        <span class="glabel">Assessed value ($)</span>
        <div class="range">
          <input
            type="number"
            placeholder={String(Math.round(ar.min))}
            value={app.filters.assessedValue?.[0] ?? ''}
            onchange={(e) =>
              app.updateFilter({
                assessedValue: rangeOrNull(
                  'assessed_value',
                  Number(e.currentTarget.value) || ar.min,
                  app.filters.assessedValue?.[1] ?? ar.max,
                ),
              })}
          />
          <span>to</span>
          <input
            type="number"
            placeholder={String(Math.round(ar.max))}
            value={app.filters.assessedValue?.[1] ?? ''}
            onchange={(e) =>
              app.updateFilter({
                assessedValue: rangeOrNull(
                  'assessed_value',
                  app.filters.assessedValue?.[0] ?? ar.min,
                  Number(e.currentTarget.value) || ar.max,
                ),
              })}
          />
        </div>
      </div>
    {/if}

    {#if facetRange(facets, 'acreage')}
      {@const acr = facetRange(facets, 'acreage')!}
      <div class="group">
        <span class="glabel">Acreage</span>
        <div class="range">
          <input
            type="number"
            placeholder={String(Math.round(acr.min))}
            value={app.filters.acreage?.[0] ?? ''}
            onchange={(e) =>
              app.updateFilter({
                acreage: rangeOrNull(
                  'acreage',
                  Number(e.currentTarget.value) || acr.min,
                  app.filters.acreage?.[1] ?? acr.max,
                ),
              })}
          />
          <span>to</span>
          <input
            type="number"
            placeholder={String(Math.round(acr.max))}
            value={app.filters.acreage?.[1] ?? ''}
            onchange={(e) =>
              app.updateFilter({
                acreage: rangeOrNull(
                  'acreage',
                  app.filters.acreage?.[0] ?? acr.min,
                  Number(e.currentTarget.value) || acr.max,
                ),
              })}
          />
        </div>
      </div>
    {/if}

    {@render checklist(
      'County',
      'county_fips',
      app.filters.countyFips,
      (v) => countyNames.get(v) ?? v,
      (v) => ({ countyFips: v }),
    )}
    {@render checklist(
      'Land use',
      'land_use_desc',
      app.filters.landUse,
      (v) => v,
      (v) => ({ landUse: v }),
    )}
  </section>
{/if}

<style>
  .fheader {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
  }
  .reset {
    background: none;
    border: none;
    color: var(--accent);
    font-size: 12px;
    padding: 0;
  }
  .reset:disabled {
    color: var(--muted);
    cursor: default;
  }
  .count {
    margin: 8px 0 10px;
    padding: 6px 10px;
    border-radius: var(--radius);
    background: var(--panel-2);
    font-size: 13px;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }
  .count.active {
    background: var(--accent-soft);
    color: #04519a;
  }
  .count.err {
    background: rgba(213, 94, 0, 0.14);
    color: #9c4500;
  }
  .group {
    margin-bottom: 11px;
  }
  .glabel {
    display: block;
    font-size: 11px;
    color: var(--muted);
    margin-bottom: 5px;
  }
  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }
  .chip {
    display: inline-flex;
    gap: 5px;
    align-items: baseline;
    padding: 3px 9px;
    font-size: 11.5px;
    border: 1px solid var(--border);
    border-radius: 999px;
    background: var(--panel);
    color: var(--text-2);
  }
  .chip.on {
    background: var(--accent);
    border-color: var(--accent);
    color: #fff;
  }
  .chip .ct {
    font-size: 10px;
    opacity: 0.7;
    font-variant-numeric: tabular-nums;
  }
  .checks {
    display: flex;
    flex-direction: column;
    gap: 3px;
  }
  .check {
    display: flex;
    align-items: center;
    gap: 7px;
    font-size: 12.5px;
    cursor: pointer;
  }
  .check input {
    margin: 0;
  }
  input[type='range'] {
    width: 100%;
  }
  .range {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .range input {
    width: 100%;
    padding: 5px 7px;
    border: 1px solid var(--border);
    border-radius: 4px;
    font-size: 12px;
    font-family: inherit;
  }
  .range span {
    font-size: 11px;
    color: var(--muted);
  }
  details.group > summary {
    font-size: 11px;
    color: var(--muted);
    cursor: pointer;
  }
  .checklist {
    max-height: 170px;
    overflow-y: auto;
    margin-top: 6px;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 6px 8px;
  }
  .checklist .check {
    padding: 2px 0;
  }
  .cl-name {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .checklist .ct {
    font-size: 10px;
    color: var(--muted);
    font-variant-numeric: tabular-nums;
  }
</style>
