<script lang="ts">
  import { store } from '../lib/audit-store.svelte';
  import { hrefs } from '../lib/router.svelte';
  import { groupFixes, overallProgress, type FixBucket } from '../lib/fixes';

  const doc = $derived(store.fixes);
  const groups = $derived(doc ? groupFixes(doc) : null);
  const progress = $derived(doc ? overallProgress(doc) : null);
  const pct = $derived(progress && progress.total ? Math.round((progress.done / progress.total) * 100) : 0);

  // The label in front of the `action` line reads differently per bucket: a fix,
  // a decision, a rework, or an un-fixable caveat.
  const ACTION_LABEL: Record<FixBucket, string> = {
    easy: 'Fix',
    medium: 'Call to make',
    macro: 'Rework',
    inherent: 'Caveat',
  };

  // dossier = `file.md#anchor` → a #/doc/<file>/<anchor> deep link.
  function dossierHref(dossier: string): string {
    const [file, anchor] = dossier.split('#');
    return hrefs.doc(file, anchor ?? null);
  }
</script>

<div class="page">
  <div class="page-head">
    <h1>Fixes</h1>
    <p class="sub">
      Every data-audit finding, bucketed by how it gets fixed — the mechanical fixes to knock out,
      and the design reworks to go hunting for. The narrative companion is
      <a href={hrefs.doc('fix-ledger.md')}>fix-ledger.md</a>.
    </p>
  </div>

  {#if doc && groups && progress}
    <!-- Honesty banner: status is a deploy-time snapshot, mirroring the
         freshness tab's framing. State how it gets updated. -->
    <p class="honesty">
      <strong>Status as of the last deploy.</strong>
      A fix is marked done by setting its <code>status</code> to <code>done</code> in
      <code>fixes.json</code>; it shows here after the next deploy. {doc.basis}
    </p>

    <!-- Overall progress across the checkable (Easy + Medium) buckets. -->
    <section class="progress" aria-label="Fix progress">
      <div class="progress-head">
        <span class="progress-n">{progress.done} <span class="of">of</span> {progress.total} fixes done</span>
        <span class="progress-pct">{pct}%</span>
      </div>
      <div class="bar" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
        <div class="bar-fill" style="width: {pct}%"></div>
      </div>
      <p class="progress-sub">Macro + Inherent items aren't counted — they're reviewed, not ticked off.</p>
    </section>

    {#each groups as g (g.bucket)}
      <section class="bucket" aria-label={g.label}>
        <div class="bucket-head">
          <h2>
            {g.label}
            {#if g.checkable}<span class="bcount">{g.done} / {g.total} done</span>{/if}
          </h2>
          <p class="meaning">{g.meaning}</p>
        </div>

        {#each g.fixes as f (f.id)}
          <article class="fix" class:is-done={f.status === 'done'}>
            <div class="fix-top">
              <span class="fid">{f.id}</span>
              {#if g.checkable}
                <span class="chip chip--{f.status === 'done' ? 'good' : 'muted'}">
                  {f.status === 'done' ? '✓ Done' : 'To do'}
                </span>
              {/if}
              <h3 class="ftitle">{f.title}</h3>
            </div>
            {#if f.problem}<p class="problem">{f.problem}</p>{/if}
            <p class="action"><strong>{ACTION_LABEL[g.bucket]}:</strong> {f.action}</p>
            <div class="meta">
              <span class="sig">{f.signal} · {f.card}</span>
              {#if f.ripple}<span class="ripple">ripple: {f.ripple}</span>{/if}
              <a class="dossier" href={dossierHref(f.dossier)}>dossier →</a>
            </div>
          </article>
        {/each}
      </section>
    {/each}
  {:else}
    <section class="placeholder" aria-label="Fix board not yet generated">
      <span class="icon" aria-hidden="true">🛠️</span>
      <h2>Fix board not yet generated</h2>
      <p>
        The fix status board (<code>fixes.json</code>) isn't available yet. This view goes live once
        it's baked into the next deploy.
      </p>
      <p class="meanwhile">
        In the meantime, the <a href={hrefs.catalog()}>Data Catalog</a> shows each data point's trust
        rating and the full audit explains every finding.
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
  .honesty code {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 0 4px;
    font-family: var(--mono);
    font-size: 0.86em;
  }

  /* ── Progress ─────────────────────────────────────────────────────────────── */
  .progress {
    padding: 14px 16px;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    box-shadow: var(--shadow);
    margin-bottom: 22px;
  }
  .progress-head {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: 9px;
  }
  .progress-n {
    font-size: 17px;
    font-weight: 700;
    letter-spacing: -0.01em;
  }
  .progress-n .of {
    color: var(--muted);
    font-weight: 500;
  }
  .progress-pct {
    font-size: 13px;
    font-weight: 600;
    color: var(--accent);
  }
  .bar {
    height: 8px;
    background: var(--panel-2);
    border-radius: 999px;
    overflow: hidden;
  }
  .bar-fill {
    height: 100%;
    background: var(--accent);
    border-radius: 999px;
    transition: width 0.3s ease;
  }
  .progress-sub {
    margin: 9px 0 0;
    font-size: 11.5px;
    color: var(--muted);
  }

  /* ── Buckets ──────────────────────────────────────────────────────────────── */
  .bucket {
    margin-bottom: 26px;
  }
  .bucket-head {
    margin-bottom: 12px;
  }
  .bucket-head h2 {
    display: flex;
    align-items: baseline;
    gap: 10px;
    font-size: 17px;
    margin: 0;
  }
  .bcount {
    font-size: 12px;
    font-weight: 600;
    color: var(--muted);
  }
  .meaning {
    margin: 4px 0 0;
    font-size: 12.5px;
    line-height: 1.5;
    color: var(--text-2);
  }

  /* ── Fix rows ─────────────────────────────────────────────────────────────── */
  .fix {
    padding: 12px 14px;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    box-shadow: var(--shadow);
    margin-bottom: 8px;
  }
  .fix.is-done {
    opacity: 0.62;
  }
  .fix-top {
    display: flex;
    align-items: center;
    gap: 9px;
    flex-wrap: wrap;
  }
  .fid {
    font-family: var(--mono);
    font-size: 11.5px;
    font-weight: 700;
    color: var(--muted);
    flex-shrink: 0;
  }
  .ftitle {
    font-size: 14px;
    font-weight: 600;
    margin: 0;
    flex: 1 1 auto;
    min-width: 0;
  }
  .fix.is-done .ftitle {
    text-decoration: line-through;
    text-decoration-color: var(--muted);
  }
  .problem {
    margin: 8px 0 0;
    font-size: 12.5px;
    line-height: 1.55;
    color: var(--text-2);
  }
  .action {
    margin: 6px 0 0;
    font-size: 12.5px;
    line-height: 1.55;
    color: var(--text);
  }
  .action strong {
    color: var(--accent);
    font-weight: 600;
  }
  .meta {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
    margin-top: 9px;
    padding-top: 8px;
    border-top: 1px solid var(--border);
    font-size: 11px;
  }
  .sig {
    font-family: var(--mono);
    color: var(--muted);
  }
  .ripple {
    color: var(--warn-fg);
  }
  .dossier {
    margin-left: auto;
    font-weight: 600;
    font-size: 11.5px;
  }

  /* ── Status chip (reused tones from the freshness strip) ──────────────────── */
  .chip {
    display: inline-flex;
    align-items: center;
    padding: 2px 8px;
    border-radius: 999px;
    font-size: 10.5px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    flex-shrink: 0;
  }
  .chip--good {
    background: color-mix(in srgb, var(--good-fg) 16%, transparent);
    color: var(--good-fg);
  }
  .chip--muted {
    background: var(--panel-2);
    color: var(--muted);
    border: 1px solid var(--border);
  }

  /* ── Placeholder ──────────────────────────────────────────────────────────── */
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
  .placeholder code {
    background: var(--panel-2);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 0 4px;
    font-family: var(--mono);
    font-size: 0.86em;
  }
  .meanwhile {
    margin-top: 14px;
    font-size: 12.5px;
    color: var(--muted);
  }

  @media (max-width: 720px) {
    .dossier {
      margin-left: 0;
    }
  }
</style>
