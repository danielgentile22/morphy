<script lang="ts">
  import { store } from '../lib/audit-store.svelte';
  import { hrefs } from '../lib/router.svelte';
  import { cardNotes } from '../lib/audit-data';
  import { statusMeta } from '../lib/tags';
  import Methods from './Methods.svelte';
  import TagRow from './TagRow.svelte';

  let { id }: { id: string } = $props();

  const card = $derived(store.cardById.get(id));
  const signals = $derived(store.signalsByCard.get(id) ?? []);
  const notes = $derived(card ? cardNotes(card) : []);
  const status = $derived(card ? statusMeta(card.status) : null);

  // output_file may be "INDEX.md+index.json"; surface the .md targets only.
  const dossierFiles = $derived(
    card ? card.output_file.split('+').filter((f) => f.endsWith('.md')) : [],
  );

  /** Split a source-doc entry into a leading URL (if any) and its trailing note. */
  function splitSource(entry: string): { url: string | null; rest: string } {
    const m = entry.match(/(https?:\/\/\S+)/);
    if (!m) return { url: null, rest: entry };
    return { url: m[1], rest: entry.replace(m[1], '').trim() };
  }
</script>

<div class="page">
  <a class="back" href={hrefs.cards}>← All cards</a>

  {#if !card}
    <div class="panel notfound">
      <h2>Card not found</h2>
      <p class="muted">No card with id <code>{id}</code> in the current index.</p>
    </div>
  {:else}
    <div class="head">
      <div class="title-row">
        <span class="mono cid">{card.id}</span>
        <h1>{card.title}</h1>
      </div>
      <div class="meta-row">
        {#if card.priority}<span class="chip chip--cat">{card.priority}</span>{/if}
        {#if status}<span class="chip chip--{status.tone}">{status.label}</span>{/if}
        <Methods methods={card.methods_done} />
        {#if card.last_audited}<span class="muted mono">audited {card.last_audited}</span>{/if}
      </div>
    </div>

    <!-- Dossier links -->
    {#if dossierFiles.length}
      <div class="dossier-links">
        {#each dossierFiles as f (f)}
          <a class="dossier-link" href={hrefs.doc(f)}>Open dossier <span class="mono">{f}</span> →</a>
        {/each}
      </div>
    {/if}

    <!-- Notes (T-90/T-91/redo/etc.) -->
    {#each notes as n (n.key)}
      <section class="note">
        <span class="note-tag">{n.label}</span>
        <p>{n.text}</p>
      </section>
    {/each}

    <!-- Signals owned -->
    <section class="sigs-section">
      <h2>Signals <span class="muted">({signals.length})</span></h2>
      {#if signals.length === 0}
        <p class="muted no-sigs">
          This card owns no signal rows — it's a {card.priority === 'P3' ? 'discovery' : 'foundation / bookend'} card
          (enumeration, discovery, reconciliation, or verification). Its findings live in the notes above and the
          dossier.
        </p>
      {:else}
        <div class="sig-list">
          {#each signals as s (s.id)}
            <a class="sig" href={hrefs.signal(s.id)}>
              <div class="sig-top">
                <span class="mono sig-id">{s.id}</span>
                <TagRow tags={s.tags} sm />
              </div>
              <p class="sig-surface muted">{s.surface}</p>
              <p class="sig-verdict">{s.verdict}</p>
            </a>
          {/each}
        </div>
      {/if}
    </section>

    <!-- Audit basis -->
    <section class="panel basis-block">
      <h2>Audit basis</h2>
      <dl class="basis">
        <div><dt>Commit</dt><dd class="mono">{card.audit_basis.commit ?? '—'}</dd></div>
        <div><dt>Data snapshot</dt><dd class="mono snap">{card.audit_basis.data_snapshot ?? '—'}</dd></div>
      </dl>
      {#if card.audit_basis.source_docs.length}
        <details class="sources">
          <summary>{card.audit_basis.source_docs.length} cited sources</summary>
          <ul>
            {#each card.audit_basis.source_docs as src, i (i)}
              {@const parts = splitSource(src)}
              <li>
                {#if parts.url}
                  <a href={parts.url} target="_blank" rel="noopener noreferrer">{parts.url}</a>
                  {#if parts.rest}<span class="muted"> {parts.rest}</span>{/if}
                {:else}
                  <span class="muted">{src}</span>
                {/if}
              </li>
            {/each}
          </ul>
        </details>
      {/if}
    </section>
  {/if}
</div>

<style>
  .back {
    display: inline-block;
    margin-bottom: 14px;
    font-size: 13px;
    font-weight: 600;
  }
  .head {
    margin-bottom: 16px;
  }
  .title-row {
    display: flex;
    align-items: baseline;
    gap: 12px;
    flex-wrap: wrap;
  }
  .cid {
    font-size: 15px;
    font-weight: 700;
    color: var(--muted);
  }
  .title-row h1 {
    font-size: 23px;
  }
  .meta-row {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-top: 10px;
    flex-wrap: wrap;
    font-size: 12px;
  }

  .dossier-links {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
    margin-bottom: 16px;
  }
  .dossier-link {
    padding: 9px 14px;
    border: 1px solid var(--accent-soft);
    background: var(--accent-bg);
    color: var(--accent);
    border-radius: var(--radius-sm);
    font-weight: 600;
    font-size: 13px;
  }
  .dossier-link:hover {
    text-decoration: none;
    border-color: var(--accent);
  }

  .note {
    border: 1px solid var(--border);
    border-left: 4px solid var(--border-strong);
    background: var(--panel-2);
    border-radius: var(--radius-sm);
    padding: 12px 14px;
    margin-bottom: 10px;
  }
  .note-tag {
    text-transform: uppercase;
    letter-spacing: 0.05em;
    font-size: 11px;
    font-weight: 700;
    color: var(--muted);
  }
  .note p {
    margin: 6px 0 0;
    font-size: 13px;
    line-height: 1.6;
    color: var(--text-2);
    white-space: pre-wrap;
  }

  .sigs-section {
    margin: 22px 0;
  }
  .sigs-section h2 {
    font-size: 16px;
    margin-bottom: 12px;
  }
  .no-sigs {
    font-size: 13.5px;
    line-height: 1.6;
    max-width: 720px;
  }
  .sig-list {
    display: grid;
    gap: 10px;
  }
  .sig {
    display: block;
    padding: 12px 14px;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    color: var(--text);
  }
  .sig:hover {
    text-decoration: none;
    border-color: var(--border-strong);
  }
  .sig-top {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
  }
  .sig-id {
    font-weight: 700;
    font-size: 13px;
  }
  .sig-surface {
    margin: 6px 0 0;
    font-size: 12px;
  }
  .sig-verdict {
    margin: 6px 0 0;
    font-size: 13px;
    line-height: 1.55;
    color: var(--text-2);
  }

  .basis-block {
    padding: 16px 18px;
    margin-top: 22px;
  }
  .basis-block h2 {
    font-size: 14px;
    margin-bottom: 12px;
  }
  .basis {
    margin: 0;
    display: grid;
    gap: 8px;
  }
  .basis > div {
    display: grid;
    grid-template-columns: 130px 1fr;
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
  .sources {
    margin-top: 14px;
  }
  .sources summary {
    cursor: pointer;
    font-weight: 600;
    font-size: 12.5px;
    color: var(--accent);
  }
  .sources ul {
    margin: 10px 0 0;
    padding-left: 18px;
    font-size: 12px;
    line-height: 1.7;
    word-break: break-all;
  }
  .notfound {
    padding: 28px;
  }

  @media (max-width: 760px) {
    .basis > div {
      grid-template-columns: 1fr;
      gap: 2px;
    }
  }
</style>
