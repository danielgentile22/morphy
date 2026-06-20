<script lang="ts">
  import { store } from '../lib/audit-store.svelte';
  import { hrefs } from '../lib/router.svelte';
  import {
    freshnessRows,
    freshnessSummary,
    statusBadge,
    statusBlurb,
    cadenceLabel,
    relativeDays,
  } from '../lib/freshness';

  const doc = $derived(store.freshness);

  // `now` is captured once per mount: every status + age below is recomputed
  // client-side against today (M9), so the due/overdue countdown advances
  // day-by-day from the baked snapshot without a redeploy.
  const now = new Date();

  const rows = $derived(doc ? freshnessRows(doc, now) : null);
  const summary = $derived(rows ? freshnessSummary(rows) : null);

  // Absolute date for tooltips / the snapshot line (locale-formatted; the
  // relative "N days ago" carries the at-a-glance read).
  function fmtDate(iso: string | null): string {
    if (!iso) return '—';
    const d = new Date(iso);
    return Number.isNaN(d.getTime())
      ? '—'
      : d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
  }

  // The per-status tiles in the summary strip, in worst-first reading order.
  const SUMMARY_ORDER = [
    { key: 'stale', label: 'Overdue', tone: 'bad' },
    { key: 'due_soon', label: 'Due soon', tone: 'warn' },
    { key: 'fresh', label: 'Fresh', tone: 'good' },
    { key: 'unknown', label: 'No schedule', tone: 'muted' },
    { key: 'rebuilt', label: 'Rebuilt', tone: 'muted' },
  ] as const;
</script>

<div class="page">
  <div class="page-head">
    <h1>What needs updating</h1>
    <p class="sub">
      A living view of each source — when it was last pulled and whether it's due or overdue —
      so the data keeps earning its keep over time.
    </p>
  </div>

  {#if doc && rows && summary}
    <!-- Honesty banner: the "last pulled" truth is a deploy-time snapshot; only
         the due/overdue countdown is live. State it plainly. -->
    <p class="honesty">
      <strong>Last pulled as of last update.</strong>
      These dates are a snapshot from the last deploy ({fmtDate(doc.generated_at)}); the
      due / overdue status below is recomputed against today, so it keeps advancing on its own.
    </p>

    <!-- Per-status count strip. -->
    <section class="strip" aria-label="Freshness summary">
      {#each SUMMARY_ORDER as tile (tile.key)}
        <div class="tile tile--{tile.tone}">
          <span class="tile-n">{summary.counts[tile.key]}</span>
          <span class="tile-l">{tile.label}</span>
        </div>
      {/each}
    </section>

    <!-- Per-source table: source · last pulled · cadence · status. -->
    <section class="table" aria-label="Source freshness">
      <div class="row row--head" aria-hidden="true">
        <span>Source</span>
        <span>Last pulled</span>
        <span>Cadence</span>
        <span>Status</span>
      </div>
      {#each rows as { source, verdict } (source.id)}
        {@const badge = statusBadge(verdict.status)}
        <div class="row">
          <div class="cell-src">
            <a class="src-title" href={hrefs.card(source.id)}>{source.title}</a>
            {#if source.rebuilt_not_fetched}
              <span class="src-sub">rebuilt, not fetched</span>
            {:else if source.manifest_source_ids.length}
              <span class="src-sub">from {source.manifest_source_ids.join(', ')}</span>
            {/if}
          </div>
          <div class="cell-pulled">
            {#if source.rebuilt_not_fetched}
              <span class="muted">—</span>
            {:else}
              <span title={fmtDate(source.last_pulled)}>{relativeDays(verdict.daysAgo)}</span>
            {/if}
          </div>
          <div class="cell-cadence">{cadenceLabel(source.cadence_days)}</div>
          <div class="cell-status">
            <span class="chip chip--{badge.tone}" title={statusBlurb(verdict.status)}>{badge.label}</span>
          </div>
        </div>
      {/each}
    </section>

    <p class="foot">
      Derived data ("rebuilt, not fetched") is rebuilt by the pipeline every run rather than pulled,
      so it has no fetch date to age. A source with no published cadence reads "No schedule" — we
      can't judge its staleness without one.
      {#if doc.manifest.last_full_check}
        <br />Manifest last swept {fmtDate(doc.manifest.last_full_check)}.
      {/if}
    </p>
  {:else}
    <section class="placeholder" aria-label="Freshness data not yet generated">
      <span class="icon" aria-hidden="true">⏳</span>
      <h2>Freshness data not yet generated</h2>
      <p>
        The last-pulled dates and due/overdue status for each source aren't available yet. This view
        goes live once the freshness snapshot is baked into the next deploy.
      </p>
      <p class="meanwhile">
        In the meantime, the <a href={hrefs.overview}>Overview</a> flags anything that looks likely to
        be stale based on each source's freshness risk, and the
        <a href={hrefs.catalog()}>Data Catalog</a> shows how current each data point is.
      </p>
    </section>
  {/if}
</div>

<style>
  .honesty {
    margin: 0 0 16px;
    padding: 11px 14px;
    font-size: 12.5px;
    line-height: 1.55;
    color: var(--text-2);
    background: var(--panel-2);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
  }
  .honesty strong {
    color: var(--text);
  }

  /* ── Summary strip ────────────────────────────────────────────────────────── */
  .strip {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 10px;
    margin-bottom: 18px;
  }
  .tile {
    display: flex;
    flex-direction: column;
    gap: 1px;
    padding: 12px 14px;
    background: var(--panel);
    border: 1px solid var(--border);
    border-left: 3px solid var(--border-strong);
    border-radius: var(--radius);
    box-shadow: var(--shadow);
  }
  .tile--bad {
    border-left-color: var(--bad-fg);
  }
  .tile--warn {
    border-left-color: var(--warn-fg);
  }
  .tile--good {
    border-left-color: var(--good-fg);
  }
  .tile--muted {
    border-left-color: var(--muted-fg);
  }
  .tile-n {
    font-size: 24px;
    font-weight: 700;
    letter-spacing: -0.02em;
    line-height: 1.1;
  }
  .tile-l {
    font-size: 11.5px;
    color: var(--muted);
  }

  /* ── Table ────────────────────────────────────────────────────────────────── */
  .table {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    box-shadow: var(--shadow);
    overflow: hidden;
  }
  .row {
    display: grid;
    grid-template-columns: minmax(0, 2.4fr) minmax(0, 1.2fr) minmax(0, 1.2fr) auto;
    gap: 12px;
    align-items: center;
    padding: 11px 16px;
    border-top: 1px solid var(--border);
  }
  .row:first-child {
    border-top: none;
  }
  .row--head {
    font-size: 10.5px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
    background: var(--panel-2);
    padding-top: 9px;
    padding-bottom: 9px;
  }
  .cell-src {
    display: flex;
    flex-direction: column;
    gap: 1px;
    min-width: 0;
  }
  .src-title {
    font-size: 13.5px;
    font-weight: 600;
    color: var(--text);
  }
  .src-sub {
    font-size: 11px;
    color: var(--muted);
    font-family: var(--mono);
  }
  .cell-pulled,
  .cell-cadence {
    font-size: 12.5px;
    color: var(--text-2);
  }
  .cell-pulled .muted {
    color: var(--muted);
  }
  .cell-status {
    justify-self: start;
  }

  .foot {
    margin: 14px 0 0;
    font-size: 11.5px;
    line-height: 1.55;
    color: var(--muted);
  }

  /* ── Placeholder (artifact not yet generated) ─────────────────────────────── */
  .placeholder {
    max-width: 560px;
    margin: 8px auto 0;
    text-align: center;
    padding: 40px 28px;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    box-shadow: var(--shadow);
  }
  .icon {
    font-size: 34px;
    line-height: 1;
    display: block;
    margin-bottom: 12px;
  }
  .placeholder h2 {
    font-size: 16px;
    margin: 0 0 8px;
  }
  .placeholder p {
    margin: 0;
    font-size: 13.5px;
    line-height: 1.55;
    color: var(--text-2);
  }
  .meanwhile {
    margin-top: 14px;
    font-size: 12.5px;
    color: var(--muted);
  }

  @media (max-width: 720px) {
    .strip {
      grid-template-columns: repeat(2, 1fr);
    }
    .row {
      grid-template-columns: minmax(0, 1.6fr) auto;
      row-gap: 4px;
    }
    .row--head {
      display: none;
    }
    .cell-cadence {
      display: none;
    }
    .cell-pulled {
      grid-column: 1;
      font-size: 11.5px;
      color: var(--muted);
    }
    .cell-status {
      grid-row: 1;
      grid-column: 2;
      justify-self: end;
    }
  }
</style>
