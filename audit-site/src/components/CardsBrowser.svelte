<script lang="ts">
  import { store } from '../lib/audit-store.svelte';
  import { hrefs } from '../lib/router.svelte';
  import { statusMeta } from '../lib/tags';
  import Methods from './Methods.svelte';

  // Cards in id order (T-00, T-01, …, T-90, T-91).
  const cards = $derived([...store.cards].sort((a, b) => a.id.localeCompare(b.id)));
  const signalsByCard = $derived(store.signalsByCard);
</script>

<div class="page page--wide">
  <div class="page-head">
    <h1>Cards</h1>
    <p class="sub">
      Each card is an independently re-runnable audit unit — one source or subsystem, its own dossier and
      signal rows. {cards.length} cards, all reconciled at the same basis.
    </p>
  </div>

  <div class="grid">
    {#each cards as c (c.id)}
      {@const count = signalsByCard.get(c.id)?.length ?? 0}
      {@const status = statusMeta(c.status)}
      <a class="tile" href={hrefs.card(c.id)}>
        <div class="tile-top">
          <span class="mono cid">{c.id}</span>
          {#if c.priority}<span class="chip chip--cat chip--sm">{c.priority}</span>{/if}
          <span class="chip chip--{status.tone} chip--sm">{status.label}</span>
        </div>
        <div class="tile-title">{c.title}</div>
        <div class="tile-foot">
          <Methods methods={c.methods_done} />
          <span class="sigs">{count} signal{count === 1 ? '' : 's'}</span>
          {#if c.last_audited}<span class="when mono">{c.last_audited}</span>{/if}
        </div>
      </a>
    {/each}
  </div>
</div>

<style>
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 14px;
  }
  .tile {
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 14px 16px;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    box-shadow: var(--shadow);
    color: var(--text);
  }
  .tile:hover {
    text-decoration: none;
    border-color: var(--border-strong);
    transform: translateY(-1px);
    transition:
      transform 0.1s,
      border-color 0.1s;
  }
  .tile-top {
    display: flex;
    align-items: center;
    gap: 7px;
  }
  .cid {
    font-weight: 700;
    font-size: 13px;
  }
  .tile-top .chip:last-child {
    margin-left: auto;
  }
  .tile-title {
    font-weight: 600;
    font-size: 15px;
    letter-spacing: -0.01em;
    line-height: 1.3;
  }
  .tile-foot {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-top: auto;
    padding-top: 6px;
  }
  .sigs {
    font-size: 12px;
    color: var(--text-2);
    font-weight: 600;
  }
  .when {
    margin-left: auto;
    font-size: 11px;
    color: var(--muted);
  }
</style>
