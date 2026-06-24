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

  // List "zoom": 0 = compact (more towers, less per card), 1 = default,
  // 2 = expanded (fewer towers, every field labelled). Per-device pref, so it
  // rides in localStorage like the last-map-view (map-view-cache.ts).
  const ZOOM_KEY = 'explore.listZoom';
  const MAX_ZOOM = 2;
  function readZoom(): number {
    try {
      const n = Number(localStorage.getItem(ZOOM_KEY));
      return Number.isInteger(n) && n >= 0 && n <= MAX_ZOOM ? n : 1;
    } catch {
      return 1;
    }
  }
  let zoom = $state(readZoom());
  function setZoom(n: number): void {
    zoom = Math.max(0, Math.min(MAX_ZOOM, n));
    try {
      localStorage.setItem(ZOOM_KEY, String(zoom));
    } catch {
      // storage disabled — the density just won't persist across reloads
    }
  }
</script>

<div class="explore-list" data-testid="explore-list">
  <div class="head">
    <span class="count" data-testid="tower-count">{rows.length} towers</span>
    {#if rows.length > CAP}<span class="capnote">showing top {CAP}</span>{/if}
    {#if shown.length > 0}
      <div class="zoom" role="group" aria-label="List density">
        <button
          data-testid="list-zoom-out"
          onclick={() => setZoom(zoom - 1)}
          disabled={zoom === 0}
          title="Show more towers, less detail"
          aria-label="Zoom out"
        >−</button>
        <button
          data-testid="list-zoom-in"
          onclick={() => setZoom(zoom + 1)}
          disabled={zoom === MAX_ZOOM}
          title="Show fewer towers, more detail"
          aria-label="Zoom in"
        >+</button>
      </div>
    {/if}
  </div>
  {#if shown.length === 0}
    <p class="empty">No towers match the current filters.</p>
  {:else}
    <div class="grid" data-testid="tower-grid" data-level={zoom}>
      {#each shown as r (r.cid + '/' + r.asr)}
        <div
          class="card"
          class:inactive={!r.active}
          data-testid="tower-row"
          data-asr={r.asr}
          tabindex="0"
          role="button"
          aria-label="Open tower {r.asr}"
          onclick={() => openTower(r.cid, r.asr)}
          onkeydown={(e) => e.key === 'Enter' && openTower(r.cid, r.asr)}
        >
          <div class="top">
            <span class="asr">{r.asr}</span>
            {#if zoom >= 1}<span class="height">{fmtHeight(r.height_m)}</span>{/if}
          </div>
          <button
            class="ownerlink"
            data-testid="tower-owner-link"
            title={towerOwnerLabel(r.owner)}
            onclick={(e) => {
              e.stopPropagation();
              openOwner(r.cid);
            }}
          >
            {towerOwnerLabel(r.owner)}
          </button>
          {#if zoom === 1}
            <div class="meta">
              <span class="state">{r.state}</span>
              <span class="sep">·</span>
              <span class="status" class:off={!r.active}>{r.active ? 'active' : 'inactive'}</span>
              <span class="sep">·</span>
              <span class="score">{fmtScore(r.score)}</span>
            </div>
          {:else if zoom >= 2}
            <dl class="kv">
              <dt>Height</dt>
              <dd>{fmtHeight(r.height_m)}</dd>
              <dt>State</dt>
              <dd>{r.state}</dd>
              <dt>Active</dt>
              <dd class="status" class:off={!r.active}>{r.active ? 'active' : 'inactive'}</dd>
              <dt>Score</dt>
              <dd>{fmtScore(r.score)}</dd>
            </dl>
          {/if}
        </div>
      {/each}
    </div>
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
  .zoom {
    margin-left: auto;
    display: inline-flex;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius);
    overflow: hidden;
  }
  .zoom button {
    width: 26px;
    height: 24px;
    padding: 0;
    border: none;
    background: var(--panel);
    color: var(--text-2);
    font-size: 15px;
    line-height: 1;
    cursor: pointer;
  }
  .zoom button + button {
    border-left: 1px solid var(--border-strong);
  }
  .zoom button:hover:not(:disabled) {
    background: var(--panel-2);
    color: var(--text);
  }
  .zoom button:disabled {
    opacity: 0.4;
    cursor: default;
  }

  /* Dense, width-filling grid: a flat 6-column table left ~half the row empty
     and showed one tower per line; these cards pack several across. The zoom
     level trades card width for detail — narrower = more towers, less per card. */
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(252px, 1fr));
    gap: 8px;
  }
  .grid[data-level='0'] {
    grid-template-columns: repeat(auto-fill, minmax(176px, 1fr));
    gap: 6px;
  }
  .grid[data-level='2'] {
    grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
    gap: 10px;
  }
  .grid[data-level='0'] .card {
    padding: 7px 10px;
  }
  .grid[data-level='2'] .card {
    padding: 12px 14px;
    gap: 6px;
  }
  .card {
    display: flex;
    flex-direction: column;
    gap: 3px;
    padding: 9px 11px;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    cursor: pointer;
    text-align: left;
  }
  .card:hover {
    border-color: var(--border-strong);
    background: var(--panel-2);
  }
  .card:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 1px;
  }
  .card.inactive {
    opacity: 0.62;
  }
  .top {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 8px;
  }
  .asr {
    font-family: var(--mono);
    font-weight: 600;
    font-size: 13px;
    letter-spacing: 0.02em;
    color: var(--text);
  }
  .height {
    font-size: 12px;
    font-variant-numeric: tabular-nums;
    color: var(--text-2);
    white-space: nowrap;
  }
  .ownerlink {
    background: none;
    border: none;
    padding: 0;
    font: inherit;
    font-size: 12.5px;
    color: var(--accent);
    text-align: left;
    cursor: pointer;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 100%;
  }
  .ownerlink:hover {
    text-decoration: underline;
  }
  .meta {
    display: flex;
    align-items: baseline;
    gap: 5px;
    font-size: 11px;
    color: var(--muted);
    font-variant-numeric: tabular-nums;
  }
  .meta .state {
    text-transform: uppercase;
    letter-spacing: 0.03em;
  }
  .meta .status.off {
    color: var(--danger);
  }
  .meta .sep {
    opacity: 0.5;
  }
  /* Expanded (zoom 2): every field labelled in a tight two-column key/value. */
  .kv {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 2px 10px;
    margin: 2px 0 0;
    font-size: 12px;
  }
  .kv dt {
    color: var(--muted);
    text-transform: uppercase;
    font-size: 10.5px;
    letter-spacing: 0.04em;
    align-self: baseline;
  }
  .kv dd {
    margin: 0;
    color: var(--text-2);
    font-variant-numeric: tabular-nums;
  }
  .kv dd.status.off {
    color: var(--danger);
  }
</style>
