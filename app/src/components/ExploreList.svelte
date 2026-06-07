<script lang="ts">
  // Explore — ranked tower list (UI overhaul P1 / #108, ADR-067). The long-list
  // lens on Explore: rows are TOWERS, ranked by score, narrowed by the SAME
  // shared filter model as the map, each linking to its owner. Clicking a row
  // opens the tower's detail (a read-only peek); the owner link opens the owner
  // page. Subsumes the old owner-grained Candidates list.
  import { exploreTowers } from '../lib/explore-towers.svelte';
  import { towerHash, leadHash } from '../lib/nav';
  import { heightFeet, towerOwnerLabel } from '../lib/towers';

  // The shared ranked-tower derivation (#119) — the SAME rows the sidebar's
  // live Towers tile counts, so list and tile can never disagree. Ranked by the
  // active scoring config (#114), narrowed by the shared filter model, with
  // archived antennas dropped unless "show archived" is on (same as the map).
  const rows = $derived(exploreTowers.rows);

  // Cap the rendered rows — there can be ~16k towers; the filter narrows them,
  // but an unfiltered list still needs a ceiling for the DOM.
  const CAP = 500;
  const shown = $derived(rows.slice(0, CAP));

  function openTower(cid: string, asr: string): void {
    // Every tower opens — an unowned tower (blank cid) still gets a page
    // (towerHash substitutes the NO_OWNER sentinel). UI overhaul round 2.
    location.hash = towerHash(cid, asr);
  }
  function openOwner(cid: string): void {
    if (cid) location.hash = leadHash(cid);
  }
  function fmtScore(s: number | null): string {
    return s == null ? '—' : s.toFixed(2);
  }
  function fmtHeight(m: number | null): string {
    const ft = heightFeet(m);
    return ft == null ? '—' : `${ft} ft`;
  }
</script>

<div class="explore-list" data-testid="explore-list">
  <div class="head">
    <span class="count" data-testid="tower-count">{rows.length} towers</span>
    {#if rows.length > CAP}<span class="capnote">showing top {CAP}</span>{/if}
  </div>
  {#if shown.length === 0}
    <p class="empty">No towers match the current filters.</p>
  {:else}
    <table class="tlist">
      <thead>
        <tr>
          <th>Score</th>
          <th>ASR</th>
          <th>Owner</th>
          <th>Height</th>
          <th>State</th>
          <th>Active</th>
        </tr>
      </thead>
      <tbody>
        {#each shown as r (r.cid + '/' + r.asr)}
          <tr
            data-testid="tower-row"
            data-asr={r.asr}
            tabindex="0"
            role="button"
            aria-label="Open tower {r.asr}"
            onclick={() => openTower(r.cid, r.asr)}
            onkeydown={(e) => e.key === 'Enter' && openTower(r.cid, r.asr)}
          >
            <td class="score">{fmtScore(r.score)}</td>
            <td>{r.asr}</td>
            <td class="owner">
              <button
                class="ownerlink"
                data-testid="tower-owner-link"
                onclick={(e) => {
                  e.stopPropagation();
                  openOwner(r.cid);
                }}
              >
                {towerOwnerLabel(r.owner)}
              </button>
            </td>
            <td>{fmtHeight(r.height_m)}</td>
            <td>{r.state}</td>
            <td>{r.active ? 'yes' : 'no'}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
</div>

<style>
  .explore-list {
    height: 100%;
    overflow-y: auto;
    background: var(--bg);
    padding: 10px 16px 28px;
  }
  .head {
    display: flex;
    align-items: baseline;
    gap: 10px;
    margin-bottom: 8px;
  }
  .count {
    font-size: 12.5px;
    font-weight: 600;
    color: var(--text-2);
  }
  .capnote {
    font-size: 11.5px;
    color: var(--muted);
  }
  .empty {
    color: var(--muted);
    font-size: 13px;
    padding: 12px 2px;
  }
  .tlist {
    width: 100%;
    border-collapse: collapse;
    font-size: 12.5px;
  }
  .tlist th {
    text-align: left;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--muted);
    padding: 6px 10px;
    border-bottom: 1px solid var(--border);
    position: sticky;
    top: 0;
    background: var(--bg);
  }
  .tlist td {
    padding: 7px 10px;
    border-bottom: 1px solid var(--border);
  }
  .tlist tbody tr {
    cursor: pointer;
  }
  .tlist tbody tr:hover {
    background: var(--panel-2);
  }
  .score {
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }
  .ownerlink {
    background: none;
    border: none;
    padding: 0;
    font: inherit;
    color: var(--accent);
    text-align: left;
    cursor: pointer;
  }
  .ownerlink:hover {
    text-decoration: underline;
  }
</style>
