<script lang="ts">
  import { onMount } from 'svelte';
  import { leads } from '../lib/leads-store.svelte';
  import { filterModel } from '../lib/filter-model.svelte';
  import { matchesOwner } from '../lib/filter-model';
  import { kindLabel, money, distressText, statusVar } from '../lib/lead-format';

  // Render cap — the discovery surface shows the top-ranked matches (the full
  // index is ~16k owners; the filter applies to ALL of them, only the table is
  // capped so the DOM stays light).
  const RENDER_CAP = 300;

  onMount(() => {
    void filterModel.load(); // the shared owners index — same source as the map
    void leads.loadMyLeads(); // which owners are advanced off New (excluded here)
    void leads.loadCounts();
  });

  // Candidates = owners at status New = the shared index minus owners advanced
  // into My-Leads. Narrowed by the SAME FilterModel + predicate the map uses
  // (one source, no forked logic), then ranked by interestingness (#52).
  const advanced = $derived(new Set(leads.myLeads.map((l) => l.display_cluster_id)));
  const candidates = $derived(
    filterModel.owners.filter((o) => !advanced.has(o.display_cluster_id)),
  );
  const matched = $derived(candidates.filter((o) => matchesOwner(o, filterModel.model)));
  const visible = $derived(
    [...matched].sort((a, b) => b.score - a.score).slice(0, RENDER_CAP),
  );

  const loading = $derived(
    filterModel.ownersStatus === 'loading' || filterModel.ownersStatus === 'idle',
  );

  function open(id: string): void {
    location.hash = `#/lead/${encodeURIComponent(id)}`;
  }
</script>

<div class="candidates" data-testid="candidates">
  <h2>Candidates</h2>
  <p class="sub">
    Landowners at status “New”, ranked by interestingness — the discovery surface. Open one to start
    working it. <span class="muted">Lead = one cross-state landowner (ADR-061).</span>
  </p>

  {#if loading}
    <p class="state-msg">Loading candidates…</p>
  {:else if filterModel.ownersStatus === 'error'}
    <p class="state-msg err" data-testid="candidates-error">
      {filterModel.ownersError}
    </p>
  {:else if filterModel.owners.length === 0}
    <p class="state-msg">
      No candidates yet. Run <code>python scripts/preprocess.py --owners-index</code> to build the
      owners index, then start the data server.
    </p>
  {:else if matched.length === 0}
    <p class="state-msg" data-testid="candidates-empty">
      No candidates match the current filters.
      <button class="linkish" onclick={() => filterModel.reset()}>Reset filters</button>
    </p>
  {:else}
    <p class="match-note" data-testid="candidates-match-note">
      {#if filterModel.active}
        {matched.length.toLocaleString()} of {candidates.length.toLocaleString()} candidates match the
        active filters{#if matched.length > visible.length} · showing top {visible.length}{/if}.
      {:else}
        {candidates.length.toLocaleString()} candidates{#if candidates.length > visible.length} · showing
          top {visible.length}{/if}.
      {/if}
    </p>
    <table class="leads">
      <thead>
        <tr>
          <th class="num"></th>
          <th>Owner</th>
          <th>Kind</th>
          <th>States</th>
          <th>Distress</th>
          <th class="num">Towers</th>
          <th class="num">Assessed</th>
          <th class="num">Score</th>
        </tr>
      </thead>
      <tbody>
        {#each visible as c, i (c.display_cluster_id)}
          <tr
            class="row"
            data-testid="candidate-row"
            onclick={() => open(c.display_cluster_id)}
            tabindex="0"
            onkeydown={(e) => e.key === 'Enter' && open(c.display_cluster_id)}
          >
            <td class="num idx">{i + 1}</td>
            <td>
              <span class="dot" style="background:{statusVar('new')}"></span>
              {c.owner_name}
            </td>
            <td>{kindLabel(c.owner_kind)}</td>
            <td>
              {#each c.states as s (s)}
                <span class="tag">{s}</span>
              {/each}
              {#if c.cross_state}
                <span class="tag x">multi-state</span>
              {/if}
            </td>
            <td class={c.distress_tier === 'distressed' ? 'distress-high' : ''}>
              {distressText(c)}
            </td>
            <td class="num">{c.tower_count}</td>
            <td class="num">{money(c.total_assessed_value)}</td>
            <td class="num">
              <span class="scorebar" style="width:{Math.round(c.score * 36)}px"></span>
              {c.score.toFixed(2)}
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
</div>

<style>
  .candidates {
    padding: 18px 22px 40px;
    max-width: 1100px;
  }
  h2 {
    font-size: 18px;
  }
  .sub {
    margin: 4px 0 16px;
    font-size: 12.5px;
    color: var(--text-2);
    max-width: 720px;
  }
  .state-msg {
    font-size: 13px;
    color: var(--muted);
  }
  .state-msg.err {
    color: var(--danger);
  }
  .match-note {
    margin: 0 0 10px;
    font-size: 12px;
    color: var(--text-2);
    font-variant-numeric: tabular-nums;
  }
  .linkish {
    background: none;
    border: none;
    color: var(--accent);
    font-size: inherit;
    padding: 0 0 0 4px;
    cursor: pointer;
  }
  code {
    font-family: var(--mono);
    background: var(--panel-2);
    padding: 1px 5px;
    border-radius: 3px;
    font-size: 11.5px;
  }
  table.leads {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: hidden;
  }
  thead th {
    text-align: left;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
    padding: 9px 12px;
    border-bottom: 1px solid var(--border);
    background: var(--panel-2);
  }
  th.num,
  td.num {
    text-align: right;
  }
  tbody td {
    padding: 9px 12px;
    border-bottom: 1px solid var(--border);
    white-space: nowrap;
  }
  tr.row {
    cursor: pointer;
  }
  tr.row:hover {
    background: var(--accent-soft);
  }
  td.idx {
    color: var(--muted);
  }
  .dot {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 999px;
    margin-right: 6px;
    vertical-align: middle;
  }
  .tag {
    display: inline-block;
    padding: 1px 6px;
    margin-right: 3px;
    font-size: 11px;
    border-radius: 3px;
    background: var(--panel-2);
    border: 1px solid var(--border);
    color: var(--text-2);
  }
  .tag.x {
    background: #efe7fb;
    border-color: #d9c8f5;
    color: #5a3aa8;
  }
  .distress-high {
    color: var(--danger);
    font-weight: 600;
  }
  .scorebar {
    display: inline-block;
    height: 8px;
    border-radius: 999px;
    background: var(--accent);
    margin-right: 6px;
    vertical-align: middle;
  }
</style>
