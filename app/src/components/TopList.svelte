<script lang="ts">
  import { app } from '../lib/stores.svelte';
  import { bboxCenter, geometryBounds } from '../lib/geo';
  import { fmtMoney, fmtScore, fmtText } from '../lib/format';
  import { ownerKindLabel } from '../lib/palette';

  const TOP_LAYER = 'interestingness_top_1000';

  // The interestingness_top_1000 view is already sorted by score desc.
  const features = $derived(app.layerData[TOP_LAYER]?.features ?? []);

  // In-memory filters over the loaded top-1000 features (Phase A scope —
  // full SQL filtering over all parcels is Phase C).
  let ownerQuery = $state('');
  let kindFilter = $state<string | null>(null);

  // Distinct owner kinds in the loaded set, most common first.
  const kinds = $derived.by(() => {
    const freq = new Map<string, number>();
    for (const f of features) {
      const k = String((f.properties ?? {}).owner_kind ?? '').trim();
      if (k) freq.set(k, (freq.get(k) ?? 0) + 1);
    }
    return [...freq.entries()].sort((a, b) => b[1] - a[1]).map(([k]) => k);
  });

  // Filtered rows — the original feature index is preserved because it is
  // the MapLibre feature id used for fly-to / highlight.
  const rows = $derived.by(() => {
    const q = ownerQuery.trim().toLowerCase();
    const out: Array<{ index: number; props: Record<string, unknown> }> = [];
    features.forEach((f, index) => {
      const props = (f.properties ?? {}) as Record<string, unknown>;
      if (q && !String(props.owner_name ?? '').toLowerCase().includes(q)) return;
      if (kindFilter && String(props.owner_kind ?? '') !== kindFilter) return;
      out.push({ index, props });
    });
    return out;
  });

  function selectRow(index: number): void {
    const f = features[index];
    if (!f) return;
    const bounds = geometryBounds(f.geometry);
    app.setSelection({
      kind: 'parcel',
      props: (f.properties ?? {}) as Record<string, unknown>,
      featureRef: { layer: TOP_LAYER, index },
      at: bounds ? bboxCenter(bounds) : undefined,
    });
  }

  function isSelected(index: number): boolean {
    const ref = app.selection?.featureRef;
    return ref?.layer === TOP_LAYER && ref.index === index;
  }
</script>

{#if features.length > 0}
  <section class="panel toplist">
    <h2>Top {features.length.toLocaleString()} parcels</h2>
    <p class="hint">Ranked by interestingness — click a row to fly there.</p>

    <input
      class="search"
      type="search"
      placeholder="Filter by owner name…"
      bind:value={ownerQuery}
      data-testid="owner-filter"
    />

    {#if kinds.length > 0}
      <div class="chips">
        <button class="chip" class:on={kindFilter === null} onclick={() => (kindFilter = null)}>
          All
        </button>
        {#each kinds as k (k)}
          <button
            class="chip"
            class:on={kindFilter === k}
            onclick={() => (kindFilter = kindFilter === k ? null : k)}
          >
            {ownerKindLabel(k)}
          </button>
        {/each}
      </div>
    {/if}

    <p class="count" data-testid="top-count">
      Showing {rows.length.toLocaleString()} of {features.length.toLocaleString()}
    </p>

    {#if rows.length === 0}
      <p class="empty">No parcels match this filter.</p>
    {:else}
      <ol class="rows" data-testid="top-list">
        {#each rows as r (r.index)}
          <li>
            <button
              type="button"
              class="row"
              class:selected={isSelected(r.index)}
              onclick={() => selectRow(r.index)}
            >
              <span class="rank">{r.index + 1}</span>
              <span class="body">
                <span class="owner">{fmtText(r.props.owner_name) ?? 'Unknown owner'}</span>
                <span class="meta">
                  {ownerKindLabel(r.props.owner_kind)}
                  {#if fmtMoney(r.props.assessed_value)}· {fmtMoney(r.props.assessed_value)}{/if}
                </span>
              </span>
              <span class="score" title="interestingness score">
                {fmtScore(r.props.interestingness_score) ?? '—'}
              </span>
            </button>
          </li>
        {/each}
      </ol>
    {/if}
  </section>
{/if}

<style>
  .hint {
    margin: 4px 0 8px;
    font-size: 12px;
    color: var(--muted);
  }
  .search {
    width: 100%;
    padding: 7px 9px;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    font-size: 13px;
    font-family: inherit;
    background: var(--bg);
  }
  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    margin-top: 8px;
  }
  .count {
    margin: 8px 0 4px;
    font-size: 11px;
    color: var(--muted);
  }
  .empty {
    font-size: 12px;
    color: var(--muted);
    font-style: italic;
  }
  .rows {
    list-style: none;
    margin: 0;
    padding: 0;
    max-height: 300px;
    overflow-y: auto;
    border: 1px solid var(--border);
    border-radius: var(--radius);
  }
  li + li .row {
    border-top: 1px solid var(--border);
  }
  .row {
    display: flex;
    align-items: center;
    gap: 10px;
    width: 100%;
    padding: 7px 10px;
    background: var(--panel);
    border: none;
    text-align: left;
    font-family: inherit;
  }
  .row:hover {
    background: var(--panel-2);
  }
  .row.selected {
    background: var(--accent-soft);
  }
  .rank {
    flex-shrink: 0;
    width: 30px;
    font-size: 11px;
    font-variant-numeric: tabular-nums;
    color: var(--muted);
    text-align: right;
  }
  .body {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
  }
  .owner {
    font-size: 12.5px;
    font-weight: 500;
    color: var(--text);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .meta {
    font-size: 11px;
    color: var(--muted);
  }
  .score {
    flex-shrink: 0;
    font-size: 12px;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    color: var(--accent);
  }
</style>
