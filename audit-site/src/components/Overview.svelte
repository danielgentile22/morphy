<script lang="ts">
  import { store } from '../lib/audit-store.svelte';
  import { hrefs } from '../lib/router.svelte';
  import { cardNotes, type Confidence } from '../lib/audit-data';
  import { emptyFilters, filtersToQuery, type FacetKey } from '../lib/signals';
  import { tagMeta } from '../lib/tags';

  const index = $derived(store.index);
  const cards = $derived(store.cards);
  const signals = $derived(store.signals);

  function countBy<T>(items: T[], key: (x: T) => string): Map<string, number> {
    const m = new Map<string, number>();
    for (const it of items) m.set(key(it), (m.get(key(it)) ?? 0) + 1);
    return m;
  }

  const confCounts = $derived(countBy(signals, (s) => s.tags.confidence));
  const statusCounts = $derived(countBy(cards, (c) => c.status));
  const priorityCounts = $derived(countBy(signals, (s) => s.priority ?? '—'));

  const cardsDone = $derived(cards.filter((c) => c.status === 'done').length);

  // A link to the Signals browser pre-filtered to one facet value.
  function facetHref(key: FacetKey, value: string): string {
    const f = emptyFilters();
    f[key] = [value];
    return hrefs.signals(filtersToQuery(f));
  }

  const CONF_ORDER: Confidence[] = ['high', 'medium', 'low'];
  const confPct = (c: Confidence) => (signals.length ? ((confCounts.get(c) ?? 0) / signals.length) * 100 : 0);

  // Watch-list: the axes that say "don't trust this for free".
  const watch = $derived([
    { label: 'low confidence', n: confCounts.get('low') ?? 0, href: facetHref('confidence', 'low') },
    {
      label: 'high derivation risk',
      n: signals.filter((s) => s.tags.derivation_risk === 'high').length,
      href: facetHref('derivation_risk', 'high'),
    },
    {
      label: 'uncheckable',
      n: signals.filter((s) => s.tags.verifiability === 'uncheckable').length,
      href: facetHref('verifiability', 'uncheckable'),
    },
    {
      label: 'high freshness risk',
      n: signals.filter((s) => s.tags.freshness_risk === 'high').length,
      href: facetHref('freshness_risk', 'high'),
    },
  ]);

  // last_audited spread across cards.
  const auditDates = $derived(
    cards.map((c) => c.last_audited).filter((d): d is string => typeof d === 'string' && d.length > 0).sort(),
  );
  const dateRange = $derived(
    auditDates.length
      ? auditDates[0] === auditDates[auditDates.length - 1]
        ? auditDates[0]
        : `${auditDates[0]} → ${auditDates[auditDates.length - 1]}`
      : '—',
  );

  // The reconciliation/verification headline lives in the cards' own notes
  // (T-90 reconcile, T-91 verify) — read them rather than restating numbers.
  const reconCard = $derived(cards.find((c) => c.id === 'T-90'));
  const verifyCard = $derived(cards.find((c) => c.id === 'T-91'));

  let notesOpen = $state(false);
</script>

<div class="page">
  <div class="page-head">
    <h1>Data Audit</h1>
    <p class="sub">
      Provenance &amp; trust verdict for every data point the product surfaces — can you spend money on
      it as-is, verify it per-instance first, or not at all?
    </p>
  </div>

  {#if index}
    <!-- Headline metrics -->
    <section class="stats">
      <a class="stat" href={hrefs.cards}>
        <span class="stat-n">{cards.length}</span>
        <span class="stat-l">cards</span>
        <span class="stat-x">{cardsDone}/{cards.length} done</span>
      </a>
      <a class="stat" href={hrefs.signals()}>
        <span class="stat-n">{signals.length}</span>
        <span class="stat-l">signals audited</span>
        <span class="stat-x">across {priorityCounts.size} priorities</span>
      </a>
      <div class="stat">
        <span class="stat-n">{confCounts.get('high') ?? 0}</span>
        <span class="stat-l">high-confidence</span>
        <span class="stat-x">act on directly</span>
      </div>
      <a class="stat stat--warnlink" href={facetHref('confidence', 'low')}>
        <span class="stat-n">{confCounts.get('low') ?? 0}</span>
        <span class="stat-l">low-confidence</span>
        <span class="stat-x">don't bet money</span>
      </a>
    </section>

    <div class="cols">
      <!-- Confidence distribution -->
      <section class="panel block">
        <h2>Confidence distribution</h2>
        <div class="bar" role="img" aria-label="Confidence distribution">
          {#each CONF_ORDER as c (c)}
            {#if (confCounts.get(c) ?? 0) > 0}
              <a
                class="seg seg--{tagMeta('confidence', c).tone}"
                href={facetHref('confidence', c)}
                style="width:{confPct(c)}%"
                title="{confCounts.get(c)} {c} ({confPct(c).toFixed(0)}%)"
              ></a>
            {/if}
          {/each}
        </div>
        <ul class="legend">
          {#each CONF_ORDER as c (c)}
            <li>
              <a href={facetHref('confidence', c)}>
                <span class="dot dot--{tagMeta('confidence', c).tone}"></span>
                <strong>{confCounts.get(c) ?? 0}</strong>
                {c}
                <span class="muted">({confPct(c).toFixed(0)}%)</span>
              </a>
            </li>
          {/each}
        </ul>
      </section>

      <!-- Watch-list -->
      <section class="panel block">
        <h2>Watch-list</h2>
        <p class="muted small">Signals flagged on a trust axis — start here.</p>
        <ul class="watch">
          {#each watch as w (w.label)}
            <li>
              <a href={w.href}>
                <span class="watch-n">{w.n}</span>
                <span class="watch-l">{w.label}</span>
              </a>
            </li>
          {/each}
        </ul>
      </section>
    </div>

    <!-- Provenance / audit basis -->
    <section class="panel block">
      <h2>Audit basis</h2>
      <dl class="basis">
        <div><dt>Generated</dt><dd class="mono">{index.generated}</dd></div>
        <div><dt>Basis commit</dt><dd class="mono">{index.audit_basis.commit ?? '—'}</dd></div>
        <div><dt>Cards last audited</dt><dd class="mono">{dateRange}</dd></div>
        <div><dt>Data snapshot</dt><dd class="mono snap">{index.audit_basis.data_snapshot ?? '—'}</dd></div>
        <div>
          <dt>Card status</dt>
          <dd>
            {#each [...statusCounts] as [status, n] (status)}
              <span class="chip chip--{status === 'done' ? 'good' : 'warn'}">{n} {status.replace('_', ' ')}</span>
            {/each}
          </dd>
        </div>
      </dl>
      <button class="notes-toggle" onclick={() => (notesOpen = !notesOpen)}>
        {notesOpen ? '▾' : '▸'} Full reconciliation note
      </button>
      {#if notesOpen}
        <p class="note">{index.note}</p>
      {/if}
    </section>

    <!-- Reconciliation & verification entry points -->
    <section class="cols">
      {#if reconCard}
        <a class="panel block recon" href={hrefs.doc(reconCard.output_file.split('+')[0])}>
          <h2>Reconciliation</h2>
          <p class="muted small">{cardNotes(reconCard)[0]?.text.slice(0, 220) ?? 'Forward + backward completeness check.'}…</p>
          <span class="go">Open reconciliation →</span>
        </a>
      {/if}
      {#if verifyCard}
        <a class="panel block recon" href={hrefs.doc(verifyCard.output_file)}>
          <h2>Adversarial verification</h2>
          <p class="muted small">{cardNotes(verifyCard)[0]?.text.slice(0, 220) ?? 'Refutation pass over every P1 verdict.'}…</p>
          <span class="go">Open verification log →</span>
        </a>
      {/if}
    </section>
  {/if}
</div>

<style>
  .stats {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 14px;
    margin-bottom: 18px;
  }
  .stat {
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 16px 18px;
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
    font-size: 30px;
    font-weight: 700;
    letter-spacing: -0.03em;
    line-height: 1.1;
  }
  .stat-l {
    font-weight: 600;
    font-size: 13px;
  }
  .stat-x {
    font-size: 11.5px;
    color: var(--muted);
  }
  .stat--warnlink .stat-n {
    color: var(--bad-fg);
  }

  .cols {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 14px;
    margin-bottom: 14px;
  }
  .block {
    padding: 16px 18px;
  }
  .block h2 {
    font-size: 14px;
    margin-bottom: 12px;
  }
  .small {
    font-size: 12px;
  }

  .bar {
    display: flex;
    height: 26px;
    border-radius: 6px;
    overflow: hidden;
    border: 1px solid var(--border);
  }
  .seg {
    display: block;
    height: 100%;
    transition: opacity 0.12s;
  }
  .seg:hover {
    opacity: 0.82;
  }
  .seg--good {
    background: var(--good-fg);
  }
  .seg--warn {
    background: var(--warn-fg);
  }
  .seg--bad {
    background: var(--bad-fg);
  }
  .legend {
    list-style: none;
    padding: 0;
    margin: 12px 0 0;
    display: flex;
    gap: 16px;
    flex-wrap: wrap;
  }
  .legend a {
    color: var(--text-2);
    display: inline-flex;
    align-items: center;
    gap: 5px;
  }
  .legend a:hover {
    text-decoration: none;
    color: var(--text);
  }
  .dot {
    width: 10px;
    height: 10px;
    border-radius: 3px;
    display: inline-block;
  }
  .dot--good {
    background: var(--good-fg);
  }
  .dot--warn {
    background: var(--warn-fg);
  }
  .dot--bad {
    background: var(--bad-fg);
  }

  .watch {
    list-style: none;
    padding: 0;
    margin: 8px 0 0;
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
  }
  .watch a {
    display: flex;
    align-items: baseline;
    gap: 8px;
    padding: 8px 10px;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    background: var(--panel-2);
    color: var(--text);
  }
  .watch a:hover {
    text-decoration: none;
    border-color: var(--border-strong);
  }
  .watch-n {
    font-size: 19px;
    font-weight: 700;
    color: var(--bad-fg);
  }
  .watch-l {
    font-size: 12.5px;
    color: var(--text-2);
  }

  .basis {
    margin: 0;
    display: grid;
    gap: 8px;
  }
  .basis > div {
    display: grid;
    grid-template-columns: 150px 1fr;
    gap: 12px;
    align-items: baseline;
  }
  .basis dt {
    color: var(--muted);
    font-size: 12px;
    font-weight: 600;
  }
  .basis dd {
    margin: 0;
    font-size: 12.5px;
    color: var(--text-2);
  }
  .basis dd.snap {
    line-height: 1.55;
  }
  .basis .chip {
    margin-right: 6px;
  }

  .notes-toggle {
    margin-top: 14px;
    background: none;
    border: none;
    color: var(--accent);
    font-weight: 600;
    font-size: 12.5px;
    padding: 0;
  }
  .note {
    margin-top: 10px;
    padding: 12px 14px;
    background: var(--panel-2);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    font-size: 12.5px;
    line-height: 1.6;
    color: var(--text-2);
    white-space: pre-wrap;
  }

  .recon {
    color: var(--text);
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .recon:hover {
    text-decoration: none;
    border-color: var(--border-strong);
  }
  .recon .go {
    margin-top: auto;
    color: var(--accent);
    font-weight: 600;
    font-size: 13px;
  }

  @media (max-width: 760px) {
    .stats {
      grid-template-columns: repeat(2, 1fr);
    }
    .cols {
      grid-template-columns: 1fr;
    }
    .basis > div {
      grid-template-columns: 1fr;
      gap: 2px;
    }
  }
</style>
