<script lang="ts">
  import { store } from '../lib/audit-store.svelte';
  import { router, hrefs } from '../lib/router.svelte';
  import { TAG_DIMENSIONS, type Signal, type TagDimension } from '../lib/audit-data';
  import {
    emptyFilters,
    filtersActive,
    filtersFromQuery,
    filtersToQuery,
    matchesFilters,
    sortSignals,
    stateOf,
    STATE_NAMES,
    type FacetKey,
    type SortKey,
  } from '../lib/signals';
  import { DIMENSION_LABELS, tagMeta } from '../lib/tags';
  import Chip from './Chip.svelte';

  let { query = '' }: { query?: string } = $props();

  // Local source of truth, seeded once from the initial URL query. Later prop
  // changes (from our own replaceState) don't reset it; "Clear" resets it.
  // svelte-ignore state_referenced_locally -- intentional one-time seed
  let filters = $state(filtersFromQuery(query));
  let sortKey = $state<SortKey>('confidence');
  let sortAsc = $state(true); // confidence asc = weakest-first (the point of the audit)

  const signals = $derived(store.signals);
  const vocab = $derived(store.vocab);

  // Reflect the filter state into the URL for shareable deep links, without
  // firing a hashchange (replaceState) so it never loops back through routing.
  $effect(() => {
    const q = filtersToQuery(filters);
    history.replaceState(null, '', q ? `#/signals?${q}` : '#/signals');
  });

  /** The facet value a signal carries for a given facet dimension. */
  function facetValue(key: FacetKey, s: Signal): string {
    switch (key) {
      case 'confidence':
        return s.tags.confidence;
      case 'priority':
        return s.priority ?? '—';
      case 'card':
        return s.card;
      case 'state':
        return stateOf(s.id) ?? 'national';
      default:
        return s.tags[key as TagDimension];
    }
  }

  interface FacetGroup {
    key: FacetKey;
    label: string;
    values: string[];
  }

  const groups = $derived.by<FacetGroup[]>(() => {
    if (!vocab) return [];
    const present = (key: FacetKey, candidates: string[]) =>
      candidates.filter((val) => signals.some((s) => facetValue(key, s) === val));
    const distinct = (vals: string[]) => [...new Set(vals)].sort();
    return [
      { key: 'confidence', label: 'Confidence', values: present('confidence', vocab.confidence) },
      { key: 'priority', label: 'Priority', values: distinct(signals.map((s) => s.priority ?? '—')) },
      { key: 'state', label: 'State', values: present('state', ['05', '12', '30', '54', 'national']) },
      { key: 'upstream_origin', label: DIMENSION_LABELS.upstream_origin, values: present('upstream_origin', vocab.upstream_origin) },
      { key: 'freshness_risk', label: DIMENSION_LABELS.freshness_risk, values: present('freshness_risk', vocab.freshness_risk) },
      { key: 'derivation_risk', label: DIMENSION_LABELS.derivation_risk, values: present('derivation_risk', vocab.derivation_risk) },
      { key: 'verifiability', label: DIMENSION_LABELS.verifiability, values: present('verifiability', vocab.verifiability) },
      { key: 'card', label: 'Card', values: distinct(signals.map((s) => s.card)) },
    ];
  });

  /** Count of signals matching every active filter except `key`, having `value`
   *  — the faceted-search count, so chips show what each toggle would yield. */
  function facetCount(key: FacetKey, value: string): number {
    const probe = { ...filters, [key]: [] as string[] };
    let n = 0;
    for (const s of signals) if (matchesFilters(s, probe) && facetValue(key, s) === value) n++;
    return n;
  }

  function facetLabel(key: FacetKey, value: string): string {
    if (key === 'state') return value === 'national' ? 'National / cross-state' : (STATE_NAMES[value] ?? value);
    if (key === 'card' || key === 'priority') return value;
    return tagMeta(key, value).label;
  }

  function toggle(key: FacetKey, value: string): void {
    const arr = filters[key];
    filters[key] = arr.includes(value) ? arr.filter((v) => v !== value) : [...arr, value];
  }

  function clearAll(): void {
    filters = emptyFilters();
  }

  function sortBy(key: SortKey): void {
    if (sortKey === key) sortAsc = !sortAsc;
    else {
      sortKey = key;
      sortAsc = true;
    }
  }

  const visible = $derived.by(() => sortSignals(signals.filter((s) => matchesFilters(s, filters)), sortKey, sortAsc));
  const active = $derived(filtersActive(filters));
  const sortArrow = (key: SortKey) => (sortKey === key ? (sortAsc ? ' ▲' : ' ▼') : '');

  const TAG_COLS: TagDimension[] = TAG_DIMENSIONS.filter((d) => d !== 'confidence');
</script>

<div class="page page--wide layout">
  <!-- Filter rail -->
  <aside class="rail">
    <div class="rail-head">
      <input
        class="search"
        type="search"
        placeholder="Search id, surface, verdict…"
        bind:value={filters.text}
        aria-label="Search signals"
      />
      {#if active}
        <button class="clear" onclick={clearAll}>Clear all</button>
      {/if}
    </div>
    {#each groups as g (g.key)}
      {#if g.values.length}
        <section class="facet">
          <h3>{g.label}</h3>
          <div class="opts">
            {#each g.values as v (v)}
              {@const count = facetCount(g.key, v)}
              <button
                class="opt"
                class:on={filters[g.key].includes(v)}
                class:zero={count === 0}
                onclick={() => toggle(g.key, v)}
                title={g.key === 'card' ? (store.cardById.get(v)?.title ?? v) : facetLabel(g.key, v)}
              >
                <span class="opt-l">{facetLabel(g.key, v)}</span>
                <span class="opt-c">{count}</span>
              </button>
            {/each}
          </div>
        </section>
      {/if}
    {/each}
  </aside>

  <!-- Results -->
  <section class="results">
    <div class="results-head">
      <h1>Signals</h1>
      <span class="count">{visible.length} of {signals.length}</span>
    </div>

    {#if visible.length === 0}
      <div class="empty panel">
        <p>No signals match these filters.</p>
        <button onclick={clearAll}>Clear all filters</button>
      </div>
    {:else}
      <div class="table-wrap panel">
        <table>
          <thead>
            <tr>
              <th class="sortable" onclick={() => sortBy('confidence')}>Conf{sortArrow('confidence')}</th>
              <th class="sortable" onclick={() => sortBy('id')}>Signal{sortArrow('id')}</th>
              <th class="sortable" onclick={() => sortBy('card')}>Card{sortArrow('card')}</th>
              <th class="sortable surface-h" onclick={() => sortBy('surface')}>Surface{sortArrow('surface')}</th>
              <th>Tags</th>
              <th>Verdict</th>
            </tr>
          </thead>
          <tbody>
            {#each visible as s (s.id)}
              {@const st = stateOf(s.id)}
              <tr onclick={() => router.go(hrefs.signal(s.id))} class="row">
                <td><Chip dimension="confidence" value={s.tags.confidence} sm /></td>
                <td class="id-cell">
                  <a href={hrefs.signal(s.id)} onclick={(e) => e.stopPropagation()} class="mono sig-id">{s.id}</a>
                  {#if st}<span class="state-badge" title={STATE_NAMES[st]}>{st}</span>{/if}
                </td>
                <td>
                  <a href={hrefs.card(s.card)} onclick={(e) => e.stopPropagation()} class="mono card-id">{s.card}</a>
                </td>
                <td class="surface">{s.surface}</td>
                <td class="tags">
                  {#each TAG_COLS as dim (dim)}
                    <Chip dimension={dim} value={s.tags[dim]} sm />
                  {/each}
                </td>
                <td class="verdict" title={s.verdict}>{s.verdict}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  </section>
</div>

<style>
  .layout {
    display: grid;
    grid-template-columns: 230px 1fr;
    gap: 20px;
    align-items: start;
  }
  .rail {
    position: sticky;
    top: calc(var(--nav-h) + 16px);
    max-height: calc(100vh - var(--nav-h) - 32px);
    overflow-y: auto;
    padding-right: 4px;
  }
  .rail-head {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin-bottom: 14px;
  }
  .search {
    width: 100%;
    padding: 7px 10px;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-sm);
    background: var(--panel);
    color: var(--text);
    font-size: 13px;
  }
  .clear {
    align-self: flex-start;
    background: none;
    border: none;
    color: var(--accent);
    font-weight: 600;
    font-size: 12px;
    padding: 0;
  }
  .facet {
    margin-bottom: 16px;
  }
  .facet h3 {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
    margin-bottom: 6px;
  }
  .opts {
    display: flex;
    flex-direction: column;
    gap: 3px;
  }
  .opt {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    padding: 4px 8px;
    border: 1px solid transparent;
    border-radius: var(--radius-sm);
    background: none;
    color: var(--text-2);
    font-size: 12.5px;
    text-align: left;
    width: 100%;
  }
  .opt:hover {
    background: var(--panel-2);
  }
  .opt.on {
    background: var(--accent-bg);
    color: var(--accent);
    border-color: var(--accent-soft);
    font-weight: 600;
  }
  .opt.zero {
    opacity: 0.4;
  }
  .opt-c {
    font-family: var(--mono);
    font-size: 11px;
    color: var(--muted);
  }
  .opt.on .opt-c {
    color: var(--accent);
  }

  .results-head {
    display: flex;
    align-items: baseline;
    gap: 12px;
    margin-bottom: 14px;
  }
  .results-head h1 {
    font-size: 22px;
  }
  .count {
    color: var(--muted);
    font-size: 13px;
    font-family: var(--mono);
  }

  .table-wrap {
    overflow-x: auto;
  }
  table {
    border-collapse: collapse;
    width: 100%;
    font-size: 12.5px;
  }
  thead th {
    position: sticky;
    top: 0;
    background: var(--panel-2);
    text-align: left;
    font-weight: 600;
    color: var(--text-2);
    padding: 8px 10px;
    border-bottom: 1px solid var(--border);
    white-space: nowrap;
    z-index: 1;
  }
  th.sortable {
    cursor: pointer;
    user-select: none;
  }
  th.sortable:hover {
    color: var(--text);
  }
  tbody td {
    padding: 8px 10px;
    border-bottom: 1px solid var(--border);
    vertical-align: top;
  }
  .row {
    cursor: pointer;
  }
  .row:hover td {
    background: var(--panel-2);
  }
  .id-cell {
    white-space: nowrap;
  }
  .sig-id {
    font-weight: 600;
  }
  .state-badge {
    margin-left: 5px;
    font-family: var(--mono);
    font-size: 10px;
    padding: 0 4px;
    border-radius: 4px;
    background: var(--muted-bg);
    color: var(--muted-fg);
    border: 1px solid var(--muted-bd);
  }
  .card-id {
    color: var(--text-2);
  }
  .surface {
    color: var(--muted);
    max-width: 190px;
    font-size: 12px;
  }
  .tags {
    white-space: nowrap;
  }
  .tags :global(.chip) {
    margin: 0 3px 3px 0;
  }
  .verdict {
    color: var(--text-2);
    min-width: 320px;
    max-width: 560px;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .empty {
    padding: 32px;
    text-align: center;
  }
  .empty button {
    margin-top: 10px;
    padding: 7px 14px;
    border: 1px solid var(--border-strong);
    background: var(--panel);
    color: var(--text);
    border-radius: var(--radius-sm);
    font-weight: 600;
  }

  @media (max-width: 880px) {
    .layout {
      grid-template-columns: 1fr;
    }
    .rail {
      position: static;
      max-height: none;
    }
    .opts {
      flex-direction: row;
      flex-wrap: wrap;
    }
    .opt {
      width: auto;
    }
  }
</style>
