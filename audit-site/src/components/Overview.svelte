<script lang="ts">
  import { store } from '../lib/audit-store.svelte';
  import { hrefs } from '../lib/router.svelte';
  import { buildCatalog, catalogStats, freshnessFlags } from '../lib/catalog';
  import { trustBadge } from '../lib/catalog-language';
  import { freshnessRows, freshnessSummary } from '../lib/freshness';

  const index = $derived(store.index);

  // Built live from index.json (the auto-populate contract): a re-run reboots the
  // app and every number here moves with it — nothing on this page is hardcoded.
  const model = $derived(index ? buildCatalog(index) : null);
  const stats = $derived(index && model ? catalogStats(index, model) : null);
  const flags = $derived(model ? freshnessFlags(model) : null);

  // Live "needs refreshing" from the deploy-time freshness snapshot, recomputed
  // against today (M9). Present ⇒ the real last-pulled view drives the callout;
  // absent (artifact not yet generated) ⇒ we fall back to the freshness-risk
  // proxy below, so the callout still renders before the first freshness deploy.
  const live = $derived(
    store.freshness
      ? freshnessSummary(freshnessRows(store.freshness, new Date()))
      : null,
  );

  // groupId → its def, so a stale point can name + deep-link to its group.
  const groupDef = $derived(
    new Map((model?.groups ?? []).map((g) => [g.def.id, g.def])),
  );

  // Per-trust counts shown beneath a card's headline badge, strongest-first; any
  // unrecognised trust value falls in after the known three (never dropped).
  const TRUST_ORDER = ['high', 'medium', 'low'];
  function orderedCounts(counts: Record<string, number>): Array<[string, number]> {
    const known = TRUST_ORDER.filter((t) => counts[t]).map((t) => [t, counts[t]] as [string, number]);
    const extra = Object.entries(counts).filter(([t]) => !TRUST_ORDER.includes(t));
    return [...known, ...extra];
  }
</script>

<div class="page">
  <div class="page-head">
    <h1>Data inventory</h1>
    <p class="sub">
      Everything we surface about a deal — how much of it there is, where it comes from, and how
      much to trust it. The one-screen view to open a meeting with.
    </p>
  </div>

  {#if index && model && stats && flags}
    <!-- Headline count strip: scope of the whole data inventory in one line. -->
    <section class="strip" aria-label="Inventory scope">
      <a class="stat" href={hrefs.catalog()}>
        <span class="stat-n">{stats.dataPoints}</span>
        <span class="stat-l">data points</span>
        <span class="stat-x">distinct things we know</span>
      </a>
      <a class="stat" href={hrefs.catalog()}>
        <span class="stat-n">{stats.sources}</span>
        <span class="stat-l">sources</span>
        <span class="stat-x">datasets behind them</span>
      </a>
      <div class="stat">
        <span class="stat-n">{stats.states}</span>
        <span class="stat-l">states</span>
        <span class="stat-x">AR · FL · MT · WV</span>
      </div>
    </section>

    <!-- Group cards: the inventory grouped by what it tells you about a deal. -->
    <section class="cards" aria-label="Data groups">
      {#each model.groups as group (group.def.id)}
        {@const badge = trustBadge(group.headlineTrust)}
        <a class="card" href={hrefs.catalog(group.def.id)}>
          <header class="card-head">
            <span class="emoji" aria-hidden="true">{group.def.emoji}</span>
            <h2>{group.def.title}</h2>
            <span class="count">{group.points.length}</span>
          </header>
          <div class="trust-line">
            <span class="chip chip--{badge.tone}" title="Most-common trust in this group">
              {badge.label} trust
            </span>
            <span class="breakdown">
              {#each orderedCounts(group.counts) as [trust, n] (trust)}
                {@const tb = trustBadge(trust)}
                <span class="bd" title="{n} {trust}">
                  <span class="bd-dot bd-dot--{tb.tone}"></span>{n}
                </span>
              {/each}
            </span>
          </div>
          {#if group.biggestCaveat}
            <p class="caveat" title="The group's lowest-confidence data point">
              <span class="caveat-l">Biggest caveat</span>
              {group.biggestCaveat}
            </p>
          {/if}
          <span class="go">View in catalog →</span>
        </a>
      {/each}
    </section>

    <!-- "Needs refreshing" callout — live from the freshness snapshot when it's
         been generated, else the Phase-1 freshness-risk proxy as a fallback. -->
    {#if live}
      <section
        class="callout"
        class:callout--alert={live.stale.length > 0}
        class:callout--ok={live.stale.length === 0 && live.dueSoon.length === 0}
        aria-label="What needs refreshing"
      >
        {#if live.stale.length > 0}
          <h2>⚠ Needs refreshing</h2>
          <p class="callout-sub">
            {live.stale.length}
            {live.stale.length === 1 ? 'source is' : 'sources are'} overdue for a refresh.
          </p>
          <ul class="stale-list">
            {#each live.stale as { source } (source.id)}
              <li>
                <a href={hrefs.card(source.id)}>
                  <span class="stale-name">{source.title}</span>
                  <span class="stale-grp">overdue</span>
                </a>
              </li>
            {/each}
          </ul>
          {#if live.dueSoon.length > 0}
            <p class="callout-soft">
              {live.dueSoon.length} more {live.dueSoon.length === 1 ? 'is' : 'are'} due soon.
            </p>
          {/if}
        {:else if live.dueSoon.length > 0}
          <h2>Nothing overdue</h2>
          <p class="callout-sub">
            {live.dueSoon.length}
            {live.dueSoon.length === 1 ? 'source is' : 'sources are'} due soon — none is overdue yet.
          </p>
        {:else}
          <h2>Everything's current</h2>
          <p class="callout-sub">Every source is within its refresh window.</p>
        {/if}
        <p class="phase-note">
          Last pulled as of last update; the due / overdue countdown advances daily.
          <a href={hrefs.freshness}>See what needs updating →</a>
        </p>
      </section>
    {:else}
      <section
        class="callout"
        class:callout--alert={flags.stale.length > 0}
        class:callout--ok={flags.stale.length === 0 && flags.canLag === 0}
        aria-label="What needs refreshing"
      >
        {#if flags.stale.length > 0}
          <h2>⚠ Needs refreshing</h2>
          <p class="callout-sub">
            {flags.stale.length}
            {flags.stale.length === 1 ? 'data point looks' : 'data points look'} likely stale.
          </p>
          <ul class="stale-list">
            {#each flags.stale as point (point.baseId)}
              <li>
                <a href={hrefs.catalog(point.groupId)}>
                  <span class="stale-name">{point.meaning ?? point.baseId}</span>
                  <span class="stale-grp">{groupDef.get(point.groupId)?.title ?? point.groupId}</span>
                </a>
              </li>
            {/each}
          </ul>
          {#if flags.canLag > 0}
            <p class="callout-soft">
              {flags.canLag} more can lag and should be refreshed periodically.
            </p>
          {/if}
        {:else if flags.canLag > 0}
          <h2>Nothing flagged as stale</h2>
          <p class="callout-sub">
            {flags.canLag} data points can lag and should be refreshed periodically — none is overdue.
          </p>
        {:else}
          <h2>Everything's current</h2>
          <p class="callout-sub">No data point is flagged for refresh.</p>
        {/if}
        <p class="phase-note">
          Based on each source's freshness risk. A live last-pulled view is coming.
        </p>
      </section>
    {/if}
  {/if}
</div>

<style>
  /* ── Count strip ──────────────────────────────────────────────────────────── */
  .strip {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 14px;
    margin-bottom: 18px;
  }
  .stat {
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 18px 20px;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    box-shadow: var(--shadow);
    color: var(--text);
  }
  a.stat:hover {
    text-decoration: none;
    border-color: var(--border-strong);
  }
  .stat-n {
    font-size: 34px;
    font-weight: 700;
    letter-spacing: -0.03em;
    line-height: 1.05;
  }
  .stat-l {
    font-weight: 600;
    font-size: 13px;
  }
  .stat-x {
    font-size: 11.5px;
    color: var(--muted);
  }

  /* ── Group cards ──────────────────────────────────────────────────────────── */
  .cards {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 14px;
    margin-bottom: 18px;
  }
  .card {
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding: 15px 16px;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    box-shadow: var(--shadow);
    color: var(--text);
  }
  .card:hover {
    text-decoration: none;
    border-color: var(--border-strong);
  }
  .card-head {
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .card-head .emoji {
    font-size: 19px;
    line-height: 1;
    flex-shrink: 0;
  }
  .card-head h2 {
    font-size: 15px;
    margin: 0;
    flex: 1 1 auto;
    min-width: 0;
  }
  .count {
    flex-shrink: 0;
    font-size: 12px;
    font-weight: 600;
    color: var(--text-2);
    background: var(--panel-2);
    border: 1px solid var(--border);
    border-radius: 100px;
    padding: 1px 9px;
  }
  .trust-line {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
  }
  .breakdown {
    display: inline-flex;
    align-items: center;
    gap: 9px;
    font-size: 11.5px;
    color: var(--muted);
  }
  .bd {
    display: inline-flex;
    align-items: center;
    gap: 4px;
  }
  .bd-dot {
    width: 8px;
    height: 8px;
    border-radius: 3px;
    display: inline-block;
  }
  .bd-dot--good {
    background: var(--good-fg);
  }
  .bd-dot--warn {
    background: var(--warn-fg);
  }
  .bd-dot--bad {
    background: var(--bad-fg);
  }
  .bd-dot--muted {
    background: var(--muted-fg);
  }
  .caveat {
    margin: 0;
    font-size: 12.5px;
    line-height: 1.5;
    color: var(--text-2);
    display: -webkit-box;
    -webkit-line-clamp: 3;
    line-clamp: 3;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .caveat-l {
    display: block;
    font-size: 10.5px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--muted);
    margin-bottom: 1px;
  }
  .go {
    margin-top: auto;
    color: var(--accent);
    font-weight: 600;
    font-size: 12.5px;
  }

  /* ── Needs-refreshing callout ─────────────────────────────────────────────── */
  .callout {
    padding: 16px 18px;
    background: var(--panel);
    border: 1px solid var(--border);
    border-left: 3px solid var(--border-strong);
    border-radius: var(--radius);
    box-shadow: var(--shadow);
    margin-bottom: 18px;
  }
  .callout--alert {
    border-left-color: var(--warn-fg);
    background: color-mix(in srgb, var(--warn-bg) 40%, var(--panel));
  }
  .callout--ok {
    border-left-color: var(--good-fg);
  }
  .callout h2 {
    font-size: 14px;
    margin: 0;
  }
  .callout-sub {
    margin: 5px 0 0;
    font-size: 13px;
    color: var(--text-2);
  }
  .stale-list {
    list-style: none;
    padding: 0;
    margin: 11px 0 0;
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
    gap: 8px;
  }
  .stale-list a {
    display: flex;
    flex-direction: column;
    gap: 1px;
    padding: 8px 11px;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    background: var(--panel-2);
    color: var(--text);
  }
  .stale-list a:hover {
    text-decoration: none;
    border-color: var(--border-strong);
  }
  .stale-name {
    font-size: 12.5px;
    font-weight: 600;
  }
  .stale-grp {
    font-size: 11px;
    color: var(--muted);
  }
  .callout-soft {
    margin: 11px 0 0;
    font-size: 12.5px;
    color: var(--text-2);
  }
  .phase-note {
    margin: 11px 0 0;
    font-size: 11.5px;
    color: var(--muted);
    font-style: italic;
  }

  @media (max-width: 620px) {
    .strip {
      grid-template-columns: 1fr;
    }
  }
</style>
