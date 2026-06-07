<script lang="ts">
  // Leads — the owner-grained work surface (UI overhaul P1 / #104, ADR-065).
  // Every owner moved off New. Two lenses on the same worklist: the kanban
  // board (MyLeads) and a flat list (mirrors Explore's map/list duality).
  import { onMount } from 'svelte';
  import { leads } from '../lib/leads-store.svelte';
  import { scoring } from '../lib/scoring-store.svelte';
  import { STATUS_LABELS } from '../lib/lead-status';
  import { kindLabel } from '../lib/lead-format';
  import { leadHash } from '../lib/nav';
  import MyLeads from './MyLeads.svelte';

  type View = 'board' | 'list';
  let view = $state<View>('board');

  // Rank the worklist by the active scoring config so switching a preset
  // re-orders Leads the same way it re-orders Explore (#115). Unknown cids
  // (not in the loaded index) sort last.
  const rankedLeads = $derived(
    [...leads.myLeads].sort(
      (a, b) =>
        (scoring.scoreOf(b.display_cluster_id) ?? -Infinity) -
        (scoring.scoreOf(a.display_cluster_id) ?? -Infinity),
    ),
  );

  onMount(() => {
    void leads.loadMyLeads();
    void leads.loadCounts();
  });

  function open(id: string): void {
    location.hash = leadHash(id);
  }
</script>

<div class="leads" data-testid="leads">
  <header class="head">
    <div class="title">
      <h2>Leads</h2>
      <span class="count" data-testid="leads-count">{leads.myLeadsCount}</span>
    </div>
    <div class="viewtoggle" role="tablist" aria-label="Leads view">
      <button
        class="vbtn"
        class:on={view === 'board'}
        data-testid="leads-view-board"
        role="tab"
        aria-selected={view === 'board'}
        onclick={() => (view = 'board')}
      >
        Board
      </button>
      <button
        class="vbtn"
        class:on={view === 'list'}
        data-testid="leads-view-list"
        role="tab"
        aria-selected={view === 'list'}
        onclick={() => (view = 'list')}
      >
        List
      </button>
    </div>
  </header>

  {#if view === 'board'}
    <MyLeads />
  {:else}
    <div class="listwrap" data-testid="leads-list">
      {#if leads.myLeadsStatus === 'loading'}
        <p class="state-msg">Loading worklist…</p>
      {:else if leads.myLeads.length === 0}
        <p class="state-msg">No leads off New yet. Pursue a tower in Explore to start one.</p>
      {:else}
        <table class="lead-table">
          <thead>
            <tr>
              <th>Owner</th>
              <th>Kind</th>
              <th>States</th>
              <th>Towers</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {#each rankedLeads as o (o.display_cluster_id)}
              <tr
                data-testid="lead-row"
                data-key={o.display_cluster_id}
                tabindex="0"
                role="button"
                aria-label="Open lead {o.owner_name}"
                onclick={() => open(o.display_cluster_id)}
                onkeydown={(e) => e.key === 'Enter' && open(o.display_cluster_id)}
              >
                <td class="owner">{o.owner_name}</td>
                <td>{kindLabel(o.owner_kind)}</td>
                <td>{o.states.join('/')}</td>
                <td>{o.tower_count}</td>
                <td>{STATUS_LABELS[o.status]}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      {/if}
    </div>
  {/if}
</div>

<style>
  .leads {
    display: flex;
    flex-direction: column;
    height: 100%;
  }
  .head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 16px 22px 6px;
    flex-shrink: 0;
  }
  .title {
    display: flex;
    align-items: baseline;
    gap: 8px;
  }
  h2 {
    font-size: 18px;
  }
  .count {
    font-size: 12px;
    font-weight: 600;
    background: var(--panel-2);
    border: 1px solid var(--border);
    border-radius: 999px;
    padding: 0 8px;
    color: var(--text-2);
  }
  .viewtoggle {
    display: inline-flex;
    border: 1px solid var(--border-strong);
    border-radius: 999px;
    overflow: hidden;
  }
  .vbtn {
    padding: 5px 14px;
    font-size: 12.5px;
    background: var(--panel);
    color: var(--text-2);
    border: none;
  }
  .vbtn.on {
    background: var(--accent);
    color: #fff;
  }
  .state-msg {
    padding: 18px 22px;
    font-size: 13px;
    color: var(--muted);
  }
  .listwrap {
    flex: 1;
    overflow-y: auto;
    padding: 8px 22px 32px;
  }
  .lead-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
  }
  .lead-table th {
    text-align: left;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--muted);
    padding: 6px 10px;
    border-bottom: 1px solid var(--border);
  }
  .lead-table td {
    padding: 8px 10px;
    border-bottom: 1px solid var(--border);
  }
  .lead-table tbody tr {
    cursor: pointer;
  }
  .lead-table tbody tr:hover {
    background: var(--panel-2);
  }
  .lead-table .owner {
    font-weight: 600;
  }
</style>
