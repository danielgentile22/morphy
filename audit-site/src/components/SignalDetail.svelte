<script lang="ts">
  import { store } from '../lib/audit-store.svelte';
  import { hrefs } from '../lib/router.svelte';
  import { TAG_DIMENSIONS, fetchDoc } from '../lib/audit-data';
  import { extractSignalSection, renderMarkdown } from '../lib/markdown';
  import { stateOf, STATE_NAMES } from '../lib/signals';
  import { DIMENSION_LABELS, tagMeta } from '../lib/tags';

  let { id }: { id: string } = $props();

  const signal = $derived(store.signalById.get(id));
  const card = $derived(signal ? store.cardById.get(signal.card) : undefined);
  const st = $derived(signal ? stateOf(signal.id) : null);
  const dossierFile = $derived(signal ? signal.dossier.split('#')[0] : '');
  const dossierAnchor = $derived(signal ? (signal.dossier.split('#')[1] ?? signal.id) : '');
  const confTone = $derived(signal ? tagMeta('confidence', signal.tags.confidence).tone : 'cat');

  let sectionHtml = $state('');
  let sectionState = $state<'loading' | 'ok' | 'missing' | 'error'>('loading');

  $effect(() => {
    const sig = signal;
    if (!sig) {
      sectionState = 'missing';
      return;
    }
    sectionState = 'loading';
    const [file, anchor] = sig.dossier.split('#');
    // The per-state dossiers key their `## Signal:` heading on the BASE id
    // (`owner_name`), while the signal id carries the `@NN` suffix — so extract
    // by the dossier anchor, not the signal id.
    fetchDoc(file)
      .then((md) => {
        const section = extractSignalSection(md, anchor ?? sig.id);
        if (section) {
          sectionHtml = renderMarkdown(section, file);
          sectionState = 'ok';
        } else {
          sectionState = 'missing';
        }
      })
      .catch(() => {
        sectionState = 'error';
      });
  });
</script>

<div class="page">
  <a class="back" href={hrefs.signals()}>← All signals</a>

  {#if !signal}
    <div class="panel notfound">
      <h2>Signal not found</h2>
      <p class="muted">No signal with id <code>{id}</code> in the current index.</p>
    </div>
  {:else}
    <div class="head">
      <div class="title-row">
        <h1 class="mono">{signal.id}</h1>
        {#if signal.priority}<span class="chip chip--cat">{signal.priority}</span>{/if}
        {#if st}<span class="chip chip--cat">{STATE_NAMES[st]}</span>{/if}
      </div>
      <p class="surface"><span class="lbl">Surfaces:</span> {signal.surface}</p>
      <p class="card-link">
        <span class="lbl">Card:</span>
        <a href={hrefs.card(signal.card)} class="mono">{signal.card}</a>
        {#if card}<span class="muted">— {card.title}</span>{/if}
      </p>
    </div>

    <div class="callout callout--{confTone}">
      <span class="callout-tag">Bottom-line verdict · {signal.tags.confidence} confidence</span>
      <p>{signal.verdict}</p>
    </div>

    <div class="cols">
      <section class="panel block">
        <h2>Trust tags</h2>
        <dl class="tags">
          {#each TAG_DIMENSIONS as dim (dim)}
            {@const meta = tagMeta(dim, signal.tags[dim])}
            <div class="tag-row">
              <dt>{DIMENSION_LABELS[dim] ?? dim}</dt>
              <dd>
                <span class="chip chip--{meta.tone}">{meta.label}</span>
                <span class="meaning">{meta.title}</span>
              </dd>
            </div>
          {/each}
        </dl>
      </section>

      <section class="panel block links">
        <h2>Source</h2>
        <a class="srclink" href={hrefs.doc(dossierFile, dossierAnchor)}>
          Full dossier section <span class="mono">{dossierFile}</span> →
        </a>
        <a class="srclink" href={hrefs.card(signal.card)}>
          Card <span class="mono">{signal.card}</span>{#if card} — {card.title}{/if} →
        </a>
      </section>
    </div>

    <section class="dossier">
      <h2>Dossier</h2>
      {#if sectionState === 'loading'}
        <p class="muted">Loading dossier…</p>
      {:else if sectionState === 'ok'}
        <article class="prose">
          <!-- Trusted in-repo dossier markdown (markdown.ts). -->
          {@html sectionHtml}
        </article>
      {:else if sectionState === 'missing'}
        <p class="muted">
          No dossier section found for <code>{signal.id}</code> in {dossierFile}.
          <a href={hrefs.doc(dossierFile, dossierAnchor)}>Open the full dossier →</a>
        </p>
      {:else}
        <p class="muted">Couldn't load {dossierFile}.</p>
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
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
  }
  .title-row h1 {
    font-size: 24px;
  }
  .surface,
  .card-link {
    margin: 8px 0 0;
    color: var(--text-2);
    font-size: 13.5px;
  }
  .lbl {
    color: var(--muted);
    font-weight: 600;
    font-size: 12px;
  }

  .callout {
    border: 1px solid var(--cat-bd);
    background: var(--cat-bg);
    border-left-width: 4px;
    border-radius: var(--radius);
    padding: 14px 16px;
    margin-bottom: 16px;
  }
  .callout--good {
    background: var(--good-bg);
    border-color: var(--good-bd);
  }
  .callout--warn {
    background: var(--warn-bg);
    border-color: var(--warn-bd);
  }
  .callout--bad {
    background: var(--bad-bg);
    border-color: var(--bad-bd);
  }
  .callout-tag {
    text-transform: uppercase;
    letter-spacing: 0.05em;
    font-size: 11px;
    font-weight: 700;
    color: var(--text-2);
  }
  .callout p {
    margin: 6px 0 0;
    font-size: 14.5px;
    line-height: 1.55;
    color: var(--text);
  }

  .cols {
    display: grid;
    grid-template-columns: 1.4fr 1fr;
    gap: 14px;
    margin-bottom: 18px;
  }
  .block {
    padding: 16px 18px;
  }
  .block h2 {
    font-size: 14px;
    margin-bottom: 12px;
  }

  .tags {
    margin: 0;
    display: grid;
    gap: 10px;
  }
  .tag-row {
    display: grid;
    grid-template-columns: 130px 1fr;
    gap: 12px;
    align-items: baseline;
  }
  .tag-row dt {
    color: var(--muted);
    font-size: 12px;
    font-weight: 600;
  }
  .tag-row dd {
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .meaning {
    font-size: 12px;
    color: var(--text-2);
  }

  .links {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .srclink {
    display: block;
    padding: 10px 12px;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    background: var(--panel-2);
    font-weight: 600;
    font-size: 13px;
  }
  .srclink:hover {
    text-decoration: none;
    border-color: var(--border-strong);
  }

  .dossier h2 {
    font-size: 15px;
    margin-bottom: 10px;
    padding-bottom: 6px;
    border-bottom: 1px solid var(--border);
  }
  .dossier .prose {
    max-width: 880px;
  }
  .notfound {
    padding: 28px;
  }

  @media (max-width: 760px) {
    .cols {
      grid-template-columns: 1fr;
    }
    .tag-row {
      grid-template-columns: 1fr;
      gap: 2px;
    }
  }
</style>
