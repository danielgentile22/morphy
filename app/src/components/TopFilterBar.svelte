<script lang="ts">
  // Slim top filter bar + "More" popover + owner/ASR search (Slice 6 / #52).
  // Replaces the parcel-centric sidebar filters. Drives the ONE shared
  // FilterModel that narrows BOTH the map's tower layer and the Candidates list.
  import { onMount } from 'svelte';
  import { app } from '../lib/stores.svelte';
  import { filterModel } from '../lib/filter-model.svelte';
  import type { FilterModel } from '../lib/filter-model';
  import type { OwnerFilterRecord } from '../lib/owners-filter-index';
  import type { TowerFeature } from '../lib/towers';
  import { kindLabel, money, feet } from '../lib/lead-format';
  import { distressTierLabel } from '../lib/palette';

  type Panel = 'state' | 'distress' | 'structure' | 'score' | 'more' | null;
  let openPanel = $state<Panel>(null);

  onMount(() => void filterModel.load());

  const m = $derived(filterModel.model);
  const stateOptions = $derived(app.index?.states ?? []);

  // county_fips → friendly name, for whatever the active state's choropleth
  // has loaded (cross-state names aren't available client-side — fall back to
  // the bare FIPS). County is a long-tail "More" filter.
  const countyNames = $derived.by(() => {
    const map = new Map<string, string>();
    for (const f of app.countyData?.features ?? []) {
      const p = (f.properties ?? {}) as Record<string, unknown>;
      if (typeof p.county_fips === 'string' && typeof p.county_name === 'string') {
        map.set(p.county_fips, p.county_name);
      }
    }
    return map;
  });
  function countyLabel(fips: string): string {
    return countyNames.get(fips) ?? fips;
  }

  // ── per-button active counts (the bar shows a small "· N" when filtering) ──
  const stateCount = $derived(m.states.length);
  const distressCount = $derived(
    m.distressTiers.length + (m.inOz ? 1 : 0) + (m.inQct ? 1 : 0) + (m.persistentPoverty ? 1 : 0),
  );
  const structureCount = $derived(m.structureTypes.length);
  const scoreCount = $derived(m.scoreMin > 0 ? 1 : 0);
  const moreCount = $derived(
    m.ownerKinds.length +
      m.countyFips.length +
      (m.portfolioMin > 1 ? 1 : 0) +
      (m.assessedValue ? 1 : 0) +
      (m.heightMin > 0 ? 1 : 0) +
      (m.activeOnly ? 1 : 0) +
      (m.structureCountMin > 1 ? 1 : 0),
  );

  function toggle(panel: Panel): void {
    openPanel = openPanel === panel ? null : panel;
  }
  function close(): void {
    openPanel = null;
  }

  function toggleIn(key: 'states' | 'distressTiers' | 'ownerKinds' | 'countyFips' | 'structureTypes', value: string): void {
    const cur = m[key];
    const next = cur.includes(value) ? cur.filter((v) => v !== value) : [...cur, value];
    filterModel.updateFilter({ [key]: next } as Partial<FilterModel>);
  }
  function setNum(key: 'scoreMin' | 'portfolioMin' | 'heightMin' | 'structureCountMin', v: number): void {
    filterModel.updateFilter({ [key]: v } as Partial<FilterModel>);
  }
  function setBool(key: 'inOz' | 'inQct' | 'persistentPoverty' | 'activeOnly', v: boolean): void {
    filterModel.updateFilter({ [key]: v } as Partial<FilterModel>);
  }
  function setAssessed(lo: number, hi: number): void {
    const max = filterModel.extents.assessedMax;
    // The full extent means "no constraint".
    filterModel.updateFilter({ assessedValue: lo <= 0 && hi >= max ? null : [lo, hi] });
  }

  // ── owner + ASR search ─────────────────────────────────────────────────
  let term = $state('');
  let ownerHits = $state<OwnerFilterRecord[]>([]);
  let asrHits = $state<TowerFeature[]>([]);
  let searchOpen = $state(false);
  let timer: ReturnType<typeof setTimeout> | null = null;

  $effect(() => () => {
    if (timer) clearTimeout(timer);
  });

  function onSearchInput(e: Event): void {
    term = (e.currentTarget as HTMLInputElement).value;
    if (timer) clearTimeout(timer);
    if (term.trim().length < 2) {
      ownerHits = [];
      asrHits = [];
      searchOpen = false;
      return;
    }
    timer = setTimeout(runSearch, 180);
  }
  function runSearch(): void {
    const q = term.trim().toLowerCase();
    ownerHits = filterModel.searchOwners(term, 6);
    asrHits = (app.towerPoints?.features ?? [])
      .filter((f) => f.properties.asr.toLowerCase().includes(q))
      .slice(0, 5) as TowerFeature[];
    searchOpen = ownerHits.length > 0 || asrHits.length > 0;
  }
  function pickOwner(o: OwnerFilterRecord): void {
    searchOpen = false;
    term = o.owner_name;
    location.hash = `#/lead/${encodeURIComponent(o.display_cluster_id)}`;
  }
  function pickAsr(f: TowerFeature): void {
    searchOpen = false;
    term = `ASR ${f.properties.asr}`;
    const [lon, lat] = f.geometry.coordinates as [number, number];
    location.hash = ''; // jump to the map
    app.flyTo([lon, lat], 13);
  }
</script>

<div class="filterbar" data-testid="top-filter-bar">
  <div class="quick">
    <button class="fbtn" class:active={stateCount} onclick={() => toggle('state')}>
      State{#if stateCount}<span class="n">· {stateCount}</span>{/if}<span class="chev">▾</span>
    </button>
    {#if openPanel === 'state'}
      <div class="popover">
        <span class="plabel">State <span class="hint">— any selected (OR)</span></span>
        <div class="chips">
          {#each stateOptions as s (s.fips)}
            <button class="chip" class:on={m.states.includes(s.abbr)} onclick={() => toggleIn('states', s.abbr)}>
              {s.abbr}
            </button>
          {/each}
        </div>
      </div>
    {/if}
  </div>

  <div class="quick">
    <button class="fbtn" class:active={distressCount} onclick={() => toggle('distress')}>
      Distress{#if distressCount}<span class="n">· {distressCount}</span>{/if}<span class="chev">▾</span>
    </button>
    {#if openPanel === 'distress'}
      <div class="popover">
        <span class="plabel">Distress tier</span>
        <div class="chips">
          {#each filterModel.distressTierOptions as t (t)}
            <button class="chip" class:on={m.distressTiers.includes(t)} onclick={() => toggleIn('distressTiers', t)}>
              {distressTierLabel(t)}
            </button>
          {/each}
        </div>
        <label class="check"><input type="checkbox" checked={m.inOz} onchange={(e) => setBool('inOz', e.currentTarget.checked)} /> Opportunity Zone</label>
        <label class="check"><input type="checkbox" checked={m.inQct} onchange={(e) => setBool('inQct', e.currentTarget.checked)} /> Qualified Census Tract</label>
        <label class="check"><input type="checkbox" checked={m.persistentPoverty} onchange={(e) => setBool('persistentPoverty', e.currentTarget.checked)} /> Persistent poverty</label>
      </div>
    {/if}
  </div>

  <div class="quick">
    <button class="fbtn" class:active={structureCount} onclick={() => toggle('structure')}>
      Structure{#if structureCount}<span class="n">· {structureCount}</span>{/if}<span class="chev">▾</span>
    </button>
    {#if openPanel === 'structure'}
      <div class="popover">
        <span class="plabel">Structure type</span>
        <div class="chips">
          {#each ['tower', 'solar'] as t (t)}
            <button class="chip" class:on={m.structureTypes.includes(t)} onclick={() => toggleIn('structureTypes', t)}>
              {t[0].toUpperCase() + t.slice(1)}
            </button>
          {/each}
        </div>
      </div>
    {/if}
  </div>

  <div class="quick">
    <button class="fbtn" class:active={scoreCount} onclick={() => toggle('score')}>
      Score{#if scoreCount}<span class="n">· ≥ {m.scoreMin.toFixed(2)}</span>{/if}<span class="chev">▾</span>
    </button>
    {#if openPanel === 'score'}
      <div class="popover">
        <span class="plabel">Interestingness score (min): {m.scoreMin.toFixed(2)}</span>
        <input
          type="range" min="0" max="1" step="0.05" value={m.scoreMin}
          oninput={(e) => setNum('scoreMin', Number(e.currentTarget.value))}
          data-testid="score-slider"
        />
      </div>
    {/if}
  </div>

  <div class="quick">
    <button class="fbtn more" class:active={moreCount} onclick={() => toggle('more')}>
      ⊕ More filters{#if moreCount}<span class="n">· {moreCount}</span>{/if}<span class="chev">▾</span>
    </button>
    {#if openPanel === 'more'}
      <div class="popover wide">
        <span class="plabel">Owner kind</span>
        <div class="chips">
          {#each filterModel.ownerKindOptions as k (k)}
            <button class="chip" class:on={m.ownerKinds.includes(k)} onclick={() => toggleIn('ownerKinds', k)}>
              {kindLabel(k)}
            </button>
          {/each}
        </div>

        <span class="plabel">Portfolio size (min parcels): {m.portfolioMin}</span>
        <input type="range" min="1" max={Math.max(filterModel.extents.portfolioMax, 1)} step="1"
          value={m.portfolioMin} oninput={(e) => setNum('portfolioMin', Number(e.currentTarget.value))} />

        <span class="plabel">Total assessed value</span>
        <div class="range">
          <input type="number" placeholder="min" value={m.assessedValue?.[0] ?? ''}
            onchange={(e) => setAssessed(Number(e.currentTarget.value) || 0, m.assessedValue?.[1] ?? filterModel.extents.assessedMax)} />
          <span>to</span>
          <input type="number" placeholder="max" value={m.assessedValue?.[1] ?? ''}
            onchange={(e) => setAssessed(m.assessedValue?.[0] ?? 0, Number(e.currentTarget.value) || filterModel.extents.assessedMax)} />
        </div>

        <span class="plabel">Tower height (min): {m.heightMin > 0 ? feet(m.heightMin) : 'any'}</span>
        <input type="range" min="0" max={Math.max(filterModel.extents.heightMax, 1)} step="1"
          value={m.heightMin} oninput={(e) => setNum('heightMin', Number(e.currentTarget.value))} />

        <span class="plabel">Structure count (min): {m.structureCountMin}</span>
        <input type="range" min="1" max={Math.max(filterModel.extents.structureCountMax, 1)} step="1"
          value={m.structureCountMin} oninput={(e) => setNum('structureCountMin', Number(e.currentTarget.value))} />

        <label class="check"><input type="checkbox" checked={m.activeOnly} onchange={(e) => setBool('activeOnly', e.currentTarget.checked)} /> Active towers only</label>

        {#if filterModel.countyOptions.length}
          <span class="plabel">County</span>
          <div class="county-list">
            {#each filterModel.countyOptions as c (c)}
              <label class="check"><input type="checkbox" checked={m.countyFips.includes(c)} onchange={() => toggleIn('countyFips', c)} /> {countyLabel(c)}</label>
            {/each}
          </div>
        {/if}
      </div>
    {/if}
  </div>

  <div class="search-wrap quick">
    <input
      type="search"
      class="search"
      placeholder="Search owner name or ASR…"
      value={term}
      oninput={onSearchInput}
      onfocus={() => (searchOpen = ownerHits.length + asrHits.length > 0)}
      data-testid="owner-search"
    />
    {#if searchOpen && (ownerHits.length || asrHits.length)}
      <div class="popover search-pop" data-testid="search-hits">
        {#if ownerHits.length}
          <span class="plabel">Owners</span>
          {#each ownerHits as o (o.display_cluster_id)}
            <button class="hit" onclick={() => pickOwner(o)}>
              <span class="hname">{o.owner_name}</span>
              <span class="hmeta">{o.states.join('/')} · {o.tower_count} twr · {money(o.total_assessed_value)}</span>
            </button>
          {/each}
        {/if}
        {#if asrHits.length}
          <span class="plabel">Towers (ASR)</span>
          {#each asrHits as f (f.properties.asr)}
            <button class="hit" onclick={() => pickAsr(f)}>
              <span class="hname">ASR {f.properties.asr}</span>
              <span class="hmeta">{f.properties.owner || 'Unknown'} · {f.properties.state}</span>
            </button>
          {/each}
        {/if}
      </div>
    {/if}
  </div>

  <button class="reset" disabled={!filterModel.active} onclick={() => filterModel.reset()} data-testid="reset-filters">
    Reset
  </button>

  {#if filterModel.active}
    <span class="active-note">{filterModel.activeCount} filter{filterModel.activeCount === 1 ? '' : 's'} active</span>
  {/if}
</div>

{#if openPanel || searchOpen}
  <!-- Click-away backdrop: closes any open popover / search dropdown. -->
  <button
    class="backdrop"
    aria-label="Close filters"
    onclick={() => {
      close();
      searchOpen = false;
    }}
  ></button>
{/if}

<style>
  .filterbar {
    position: relative;
    z-index: 30;
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    padding: 8px 12px;
    background: var(--panel);
    border-bottom: 1px solid var(--border);
  }
  .quick {
    position: relative;
  }
  .fbtn {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 6px 11px;
    border: 1px solid var(--border);
    border-radius: 999px;
    background: var(--panel);
    color: var(--text-1, #1a1f28);
    font-size: 12.5px;
    font-family: inherit;
    cursor: pointer;
  }
  .fbtn:hover {
    border-color: var(--accent);
  }
  .fbtn.active {
    background: var(--accent-soft);
    border-color: var(--accent);
    color: #04519a;
  }
  .fbtn.more {
    font-weight: 600;
  }
  .fbtn .n {
    font-variant-numeric: tabular-nums;
    font-size: 11.5px;
  }
  .chev {
    font-size: 9px;
    opacity: 0.6;
  }
  .popover {
    position: absolute;
    top: calc(100% + 6px);
    left: 0;
    z-index: 35;
    min-width: 240px;
    max-width: 340px;
    padding: 12px 14px;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    box-shadow: var(--shadow, 0 6px 24px rgba(0, 0, 0, 0.16));
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .popover.wide {
    min-width: 300px;
  }
  .plabel {
    font-size: 11px;
    color: var(--muted);
    margin-top: 2px;
  }
  .hint {
    text-transform: none;
    font-style: italic;
  }
  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
  }
  .chip {
    padding: 3px 9px;
    border: 1px solid var(--border);
    border-radius: 999px;
    background: var(--panel);
    font-size: 12px;
    font-family: inherit;
    cursor: pointer;
  }
  .chip.on {
    background: var(--accent);
    border-color: var(--accent);
    color: #fff;
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
  .county-list {
    max-height: 180px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 3px;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 6px 8px;
  }
  .search-wrap {
    flex: 1;
    min-width: 200px;
    max-width: 360px;
  }
  .search {
    width: 100%;
    padding: 7px 11px;
    border: 1px solid var(--border);
    border-radius: 999px;
    font-size: 12.5px;
    font-family: inherit;
    background: var(--bg, #fff);
  }
  .search-pop {
    left: 0;
    right: 0;
    min-width: 0;
    max-width: none;
    max-height: 320px;
    overflow-y: auto;
    gap: 2px;
  }
  .hit {
    display: flex;
    flex-direction: column;
    gap: 1px;
    width: 100%;
    padding: 6px 8px;
    border: none;
    border-radius: 6px;
    background: var(--panel);
    text-align: left;
    cursor: pointer;
  }
  .hit:hover {
    background: var(--accent-soft);
  }
  .hname {
    font-size: 12.5px;
    font-weight: 500;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .hmeta {
    font-size: 11px;
    color: var(--muted);
  }
  .reset {
    margin-left: 4px;
    background: none;
    border: none;
    color: var(--accent);
    font-size: 12px;
    cursor: pointer;
  }
  .reset:disabled {
    color: var(--muted);
    cursor: default;
  }
  .active-note {
    font-size: 11.5px;
    color: var(--muted);
  }
  .backdrop {
    position: fixed;
    inset: 0;
    z-index: 25;
    background: transparent;
    border: none;
    padding: 0;
    cursor: default;
  }
</style>
