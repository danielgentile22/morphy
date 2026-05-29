<script lang="ts">
  import { app } from '../lib/stores.svelte';
  import { duckDb, type OwnerSearchHit } from '../lib/duckdb';
  import { fmtInt } from '../lib/format';

  let ownerTerm = $state('');
  let ownerHits = $state<OwnerSearchHit[]>([]);
  let ownerSearching = $state(false);
  let ownerTimer: ReturnType<typeof setTimeout> | null = null;
  // Monotonic request tokens — a slow response is discarded if a newer
  // search of the same kind has since started, so stale results can't
  // overwrite newer ones. Owner / APN searches are independent.
  let ownerToken = 0;
  let apnToken = 0;

  let apnTerm = $state('');
  let apnStatus = $state<'idle' | 'searching' | 'notfound'>('idle');

  // Cancel a pending debounce so it can't fire after the component unmounts.
  $effect(() => () => {
    if (ownerTimer) clearTimeout(ownerTimer);
  });

  function onOwnerInput(e: Event): void {
    ownerTerm = (e.currentTarget as HTMLInputElement).value;
    apnStatus = 'idle';
    if (ownerTimer) clearTimeout(ownerTimer);
    if (ownerTerm.trim().length < 2) {
      ownerHits = [];
      ownerSearching = false;
      return;
    }
    // Debounced 200 ms — a keystroke should not fire a query each press.
    const token = ++ownerToken;
    ownerSearching = true;
    ownerTimer = setTimeout(async () => {
      const hits = await duckDb.searchOwners(ownerTerm).catch(() => []);
      if (token !== ownerToken) return; // superseded by a newer query
      ownerHits = hits;
      ownerSearching = false;
    }, 200);
  }

  function pickOwner(hit: OwnerSearchHit): void {
    app.updateFilter({ ownerClusterId: hit.owner_cluster_id });
    ++ownerToken; // invalidate any in-flight owner query
    ownerHits = [];
    ownerSearching = false;
    ownerTerm = hit.owner_name;
  }

  async function onApnSubmit(e: SubmitEvent): Promise<void> {
    e.preventDefault();
    if (!apnTerm.trim()) return;
    const token = ++apnToken;
    apnStatus = 'searching';
    const found = await app.selectParcelByApn(apnTerm);
    if (token !== apnToken) return; // a newer APN search superseded this one
    apnStatus = found ? 'idle' : 'notfound';
  }
</script>

{#if app.filtersAvailable}
  <section class="panel" data-testid="search-panel">
    <h2>Search</h2>

    <div class="field">
      <input
        type="search"
        placeholder="Owner name…"
        value={ownerTerm}
        oninput={onOwnerInput}
        data-testid="owner-search"
      />
      {#if ownerSearching}
        <p class="hint">Searching…</p>
      {/if}
      {#if ownerHits.length > 0}
        <ul class="hits" data-testid="owner-hits">
          {#each ownerHits as hit (hit.owner_cluster_id)}
            <li>
              <button type="button" onclick={() => pickOwner(hit)}>
                <span class="hname">{hit.owner_name}</span>
                <span class="hmeta">{fmtInt(hit.owner_cluster_size)} parcels</span>
              </button>
            </li>
          {/each}
        </ul>
      {/if}
    </div>

    <form class="field" onsubmit={onApnSubmit}>
      <input
        type="search"
        placeholder="Parcel ID (APN)… ↵"
        bind:value={apnTerm}
        data-testid="apn-search"
      />
      {#if apnStatus === 'notfound'}
        <p class="hint err">No parcel with that ID.</p>
      {/if}
    </form>
  </section>
{/if}

<style>
  .field {
    margin-bottom: 9px;
    position: relative;
  }
  .field:last-child {
    margin-bottom: 0;
  }
  input {
    width: 100%;
    padding: 7px 9px;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    font-size: 13px;
    font-family: inherit;
    background: var(--bg);
  }
  .hint {
    margin: 4px 0 0;
    font-size: 11px;
    color: var(--muted);
  }
  .hint.err {
    color: var(--danger);
  }
  .hits {
    list-style: none;
    margin: 4px 0 0;
    padding: 0;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    max-height: 220px;
    overflow-y: auto;
  }
  .hits li + li button {
    border-top: 1px solid var(--border);
  }
  .hits button {
    display: flex;
    flex-direction: column;
    width: 100%;
    padding: 6px 9px;
    background: var(--panel);
    border: none;
    text-align: left;
  }
  .hits button:hover {
    background: var(--panel-2);
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
