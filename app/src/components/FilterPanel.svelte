<script lang="ts">
  // The single filter surface (UI overhaul #119): every filter relocated from
  // the old top bar into a vertical sidebar panel. Each filter is an
  // individually collapsible <details> section (so the panel stays scannable
  // and a set-and-forget filter can be tucked away), with an "active" dot so a
  // collapsed-but-applied filter is still visible. Drives the ONE shared
  // FilterModel that narrows BOTH the map's tower layer and the candidates list.
  import { onMount } from 'svelte';
  import { app } from '../lib/stores.svelte';
  import { filterModel } from '../lib/filter-model.svelte';
  import { archivedAntennas } from '../lib/archived-antennas.svelte';
  import type { FilterModel } from '../lib/filter-model';
  import type { OwnerFilterRecord } from '../lib/owners-filter-index';
  import type { TowerFeature } from '../lib/towers';
  import { kindLabel, money, feet } from '../lib/lead-format';
  import { distressTierLabel } from '../lib/palette';
  import { COUNTIES_LAYER } from '../lib/county-layers';

  onMount(() => void filterModel.load());

  const m = $derived(filterModel.model);
  const stateOptions = $derived(app.index?.states ?? []);

  // ── debounced numeric commits (PERF-002) ───────────────────────────────
  // Each slider tick used to commit immediately, and every commit rescans
  // 16,237 owners + re-clusters 80,814 towers — ~20× per drag. Keep the thumb
  // responsive via a local mirror, and debounce the (expensive) model commit.
  const FILTER_DEBOUNCE_MS = 140;
  let scoreMinLocal = $state(filterModel.model.scoreMin);
  let portfolioMinLocal = $state(filterModel.model.portfolioMin);
  let heightMinLocal = $state(filterModel.model.heightMin);
  let structureCountMinLocal = $state(filterModel.model.structureCountMin);
  // Keep the mirrors in step when the model changes elsewhere (reset, a saved
  // default, a deep link) so the thumbs follow.
  $effect(() => void (scoreMinLocal = filterModel.model.scoreMin));
  $effect(() => void (portfolioMinLocal = filterModel.model.portfolioMin));
  $effect(() => void (heightMinLocal = filterModel.model.heightMin));
  $effect(() => void (structureCountMinLocal = filterModel.model.structureCountMin));

  let commitTimer: ReturnType<typeof setTimeout> | null = null;
  let pending: Partial<FilterModel> = {};
  function commitDebounced(patch: Partial<FilterModel>): void {
    pending = { ...pending, ...patch };
    if (commitTimer) clearTimeout(commitTimer);
    commitTimer = setTimeout(flushCommit, FILTER_DEBOUNCE_MS);
  }
  function flushCommit(): void {
    if (commitTimer) {
      clearTimeout(commitTimer);
      commitTimer = null;
    }
    if (Object.keys(pending).length === 0) return;
    filterModel.updateFilter(pending);
    pending = {};
  }
  function cancelPending(): void {
    if (commitTimer) {
      clearTimeout(commitTimer);
      commitTimer = null;
    }
    pending = {};
  }
  function resetFilters(): void {
    cancelPending(); // a queued slider commit must not resurrect a reset value
    filterModel.reset();
  }

  // Per-filter "is this constraining?" flags — drive the active dot on each
  // collapsible header so a tucked-away filter still announces itself.
  const distressActive = $derived(
    m.distressTiers.length > 0 || m.inOz || m.inQct || m.persistentPoverty,
  );
  const optionsActive = $derived(m.activeOnly || archivedAntennas.show);

  function toggleIn(
    key: 'states' | 'distressTiers' | 'ownerKinds' | 'structureTypes',
    value: string,
  ): void {
    const cur = m[key];
    const next = cur.includes(value) ? cur.filter((v) => v !== value) : [...cur, value];
    filterModel.updateFilter({ [key]: next } as Partial<FilterModel>);
  }
  function setNum(key: 'scoreMin' | 'portfolioMin' | 'heightMin' | 'structureCountMin', v: number): void {
    commitDebounced({ [key]: v } as Partial<FilterModel>);
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
    flushCommit(); // commit any in-flight slider value before unmount (collapse)
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
    // Short-circuit after 5 ASR hits instead of scanning all 80,814 features
    // (PERF-035) — the popover shows at most 5 anyway.
    const hits: TowerFeature[] = [];
    for (const f of app.towerPoints?.features ?? []) {
      if (f.properties.asr.toLowerCase().includes(q)) {
        hits.push(f as TowerFeature);
        if (hits.length >= 5) break;
      }
    }
    asrHits = hits;
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

<div class="filter-panel" data-testid="filter-panel">
  <div class="fp-head">
    <span class="fp-title">Filters</span>
    {#if filterModel.active}
      <span class="active-note" data-testid="active-count">{filterModel.activeCount} active</span>
    {/if}
    <button
      class="reset"
      disabled={!filterModel.active}
      onclick={resetFilters}
      data-testid="reset-filters"
    >
      Reset
    </button>
  </div>

  <!-- Owner / ASR search lives with the rest of the filtering tools (#119). -->
  <div class="search-wrap">
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

  <details class="group" open>
    <summary class="ghead">
      <span class="chev" aria-hidden="true">›</span>
      <span class="gtitle">State</span>
      {#if m.states.length}<span class="dot" data-testid="filter-active-state"></span>{/if}
    </summary>
    <div class="group-body">
      <span class="hint">Any selected (OR)</span>
      <div class="chips">
        {#each stateOptions as s (s.fips)}
          <button class="chip" class:on={m.states.includes(s.abbr)} onclick={() => toggleIn('states', s.abbr)}>
            {s.abbr}
          </button>
        {/each}
      </div>
    </div>
  </details>

  <details class="group" open>
    <summary class="ghead">
      <span class="chev" aria-hidden="true">›</span>
      <span class="gtitle">Structure type</span>
      {#if m.structureTypes.length}<span class="dot"></span>{/if}
    </summary>
    <div class="group-body">
      <div class="chips">
        {#each ['tower', 'solar'] as t (t)}
          <button class="chip" class:on={m.structureTypes.includes(t)} onclick={() => toggleIn('structureTypes', t)}>
            {t[0].toUpperCase() + t.slice(1)}
          </button>
        {/each}
      </div>
    </div>
  </details>

  <details class="group" open>
    <summary class="ghead">
      <span class="chev" aria-hidden="true">›</span>
      <span class="gtitle">Distress</span>
      {#if distressActive}<span class="dot"></span>{/if}
    </summary>
    <div class="group-body">
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
      <!-- Map display, not a filter: shades counties by ARC distress tier at
           low zoom (audit M-d / #209). Doesn't constrain owners, so it never
           lights the group's active dot. -->
      <label class="check" data-testid="county-shading-toggle">
        <input
          type="checkbox"
          checked={app.isLayerVisible(COUNTIES_LAYER)}
          onchange={(e) => app.setLayerVisible(COUNTIES_LAYER, e.currentTarget.checked)}
        />
        Shade counties by distress
      </label>
    </div>
  </details>

  <details class="group" open>
    <summary class="ghead">
      <span class="chev" aria-hidden="true">›</span>
      <span class="gtitle">Interestingness score</span>
      {#if m.scoreMin > 0}<span class="dot"></span>{/if}
    </summary>
    <div class="group-body">
      <span class="glabel">Minimum: {scoreMinLocal.toFixed(2)}</span>
      <input
        type="range" min="0" max="1" step="0.05" value={scoreMinLocal}
        oninput={(e) => { scoreMinLocal = Number(e.currentTarget.value); setNum('scoreMin', scoreMinLocal); }}
        data-testid="score-slider"
      />
    </div>
  </details>

  <details class="group" open>
    <summary class="ghead">
      <span class="chev" aria-hidden="true">›</span>
      <span class="gtitle">Owner kind</span>
      {#if m.ownerKinds.length}<span class="dot"></span>{/if}
    </summary>
    <div class="group-body">
      <div class="chips">
        {#each filterModel.ownerKindOptions as k (k)}
          <button class="chip" class:on={m.ownerKinds.includes(k)} onclick={() => toggleIn('ownerKinds', k)}>
            {kindLabel(k)}
          </button>
        {/each}
      </div>
    </div>
  </details>

  <details class="group">
    <summary class="ghead">
      <span class="chev" aria-hidden="true">›</span>
      <span class="gtitle">Portfolio size</span>
      {#if m.portfolioMin > 1}<span class="dot"></span>{/if}
    </summary>
    <div class="group-body">
      <span class="glabel">Min parcels: {portfolioMinLocal}</span>
      <input type="range" min="1" max={Math.max(filterModel.extents.portfolioMax, 1)} step="1"
        value={portfolioMinLocal}
        oninput={(e) => { portfolioMinLocal = Number(e.currentTarget.value); setNum('portfolioMin', portfolioMinLocal); }} />
    </div>
  </details>

  <details class="group">
    <summary class="ghead">
      <span class="chev" aria-hidden="true">›</span>
      <span class="gtitle">Total market value</span>
      {#if m.assessedValue}<span class="dot"></span>{/if}
    </summary>
    <div class="group-body">
      <div class="range">
        <input type="number" placeholder="min" value={m.assessedValue?.[0] ?? ''}
          onchange={(e) => setAssessed(Number(e.currentTarget.value) || 0, m.assessedValue?.[1] ?? filterModel.extents.assessedMax)} />
        <span>to</span>
        <input type="number" placeholder="max" value={m.assessedValue?.[1] ?? ''}
          onchange={(e) => setAssessed(m.assessedValue?.[0] ?? 0, Number(e.currentTarget.value) || filterModel.extents.assessedMax)} />
      </div>
    </div>
  </details>

  <details class="group">
    <summary class="ghead">
      <span class="chev" aria-hidden="true">›</span>
      <span class="gtitle">Tower height</span>
      {#if m.heightMin > 0}<span class="dot"></span>{/if}
    </summary>
    <div class="group-body">
      <span class="glabel">Min: {heightMinLocal > 0 ? feet(heightMinLocal) : 'any'}</span>
      <input type="range" min="0" max={Math.max(filterModel.extents.heightMax, 1)} step="1"
        value={heightMinLocal}
        oninput={(e) => { heightMinLocal = Number(e.currentTarget.value); setNum('heightMin', heightMinLocal); }} />
    </div>
  </details>

  <details class="group">
    <summary class="ghead">
      <span class="chev" aria-hidden="true">›</span>
      <span class="gtitle">Structure count</span>
      {#if m.structureCountMin > 1}<span class="dot"></span>{/if}
    </summary>
    <div class="group-body">
      <span class="glabel">Min: {structureCountMinLocal}</span>
      <input type="range" min="1" max={Math.max(filterModel.extents.structureCountMax, 1)} step="1"
        value={structureCountMinLocal}
        oninput={(e) => { structureCountMinLocal = Number(e.currentTarget.value); setNum('structureCountMin', structureCountMinLocal); }} />
    </div>
  </details>

  <details class="group">
    <summary class="ghead">
      <span class="chev" aria-hidden="true">›</span>
      <span class="gtitle">Options</span>
      {#if optionsActive}<span class="dot"></span>{/if}
    </summary>
    <div class="group-body">
      <label class="check"><input type="checkbox" checked={m.activeOnly} onchange={(e) => setBool('activeOnly', e.currentTarget.checked)} /> Active towers only</label>
      <!-- Per-antenna archive (UI overhaul round 2): off = archived antennas are
           hidden from the map + list; on = reveal them (to recover one). -->
      <label class="check">
        <input
          type="checkbox"
          checked={archivedAntennas.show}
          onchange={(e) => archivedAntennas.setShow(e.currentTarget.checked)}
          data-testid="show-archived"
        /> Show archived antennas
      </label>
    </div>
  </details>
</div>

<style>
  .filter-panel {
    display: flex;
    flex-direction: column;
    gap: 0;
  }
  .fp-head {
    display: flex;
    align-items: baseline;
    gap: 8px;
    padding: 12px 16px 10px;
  }
  .fp-title {
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--muted);
  }
  .active-note {
    font-size: 11.5px;
    color: var(--accent);
    font-weight: 500;
  }
  .reset {
    margin-left: auto;
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

  .search-wrap {
    position: relative;
    padding: 0 16px 12px;
  }
  .search {
    width: 100%;
    padding: 7px 11px;
    border: 1px solid var(--border);
    border-radius: 999px;
    font-size: 12.5px;
    font-family: inherit;
    background: var(--panel);
    color: var(--text);
  }

  /* Each filter is a collapsible <details> section (#119 follow-up). */
  .group {
    border-top: 1px solid var(--border);
  }
  .ghead {
    list-style: none;
    cursor: pointer;
    user-select: none;
    display: flex;
    align-items: center;
    gap: 7px;
    padding: 11px 16px;
  }
  .ghead::-webkit-details-marker {
    display: none;
  }
  .gtitle {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: var(--muted);
  }
  .chev {
    font-size: 13px;
    line-height: 1;
    color: var(--muted);
    transition: transform 0.12s ease;
  }
  .group[open] > .ghead .chev {
    transform: rotate(90deg);
  }
  .ghead:hover .gtitle,
  .ghead:hover .chev {
    color: var(--text-2);
  }
  /* "This filter is constraining" marker, shown even when collapsed. */
  .dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--accent);
  }
  .group-body {
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 0 16px 12px;
  }
  .glabel {
    font-size: 11px;
    color: var(--muted);
  }
  .hint {
    font-size: 11px;
    color: var(--muted);
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
    background: var(--panel);
    color: var(--text);
  }
  .range span {
    font-size: 11px;
    color: var(--muted);
  }
  .popover {
    position: absolute;
    z-index: 35;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    box-shadow: var(--shadow, 0 6px 24px rgba(0, 0, 0, 0.16));
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 8px;
  }
  .plabel {
    font-size: 11px;
    color: var(--muted);
    margin-top: 2px;
  }
  .search-pop {
    top: calc(100% - 6px);
    left: 16px;
    right: 16px;
    max-height: 320px;
    overflow-y: auto;
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
</style>
