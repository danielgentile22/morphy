<script lang="ts">
  import { fetchDoc } from '../lib/audit-data';
  import { renderMarkdown } from '../lib/markdown';

  let { file, anchor = null }: { file: string; anchor?: string | null } = $props();

  let html = $state('');
  let loading = $state(true);
  let error = $state<string | null>(null);
  let container = $state<HTMLElement | null>(null);

  // (Re)load whenever the file changes.
  $effect(() => {
    const current = file;
    loading = true;
    error = null;
    html = '';
    fetchDoc(current)
      .then((md) => {
        html = renderMarkdown(md, current);
      })
      .catch((err: unknown) => {
        error = err instanceof Error ? err.message : String(err);
      })
      .finally(() => {
        loading = false;
      });
  });

  // After the html is in the DOM, scroll to the anchor (signal→dossier
  // deep-link) or to the top. Re-runs when anchor or html changes.
  $effect(() => {
    const a = anchor;
    if (!html || !container) return;
    const root = container;
    requestAnimationFrame(() => {
      if (a) {
        const el = root.querySelector(`[id="${a}"]`);
        if (el) {
          el.scrollIntoView({ block: 'start' });
          return;
        }
      }
      window.scrollTo({ top: 0 });
    });
  });
</script>

<div class="page page--wide">
  <div class="docbar">
    <span class="mono filename">{file}</span>
    {#if anchor}<span class="muted">#{anchor}</span>{/if}
  </div>

  {#if loading}
    <p class="muted">Loading {file}…</p>
  {:else if error}
    <div class="panel err">
      <strong>Couldn't load {file}</strong>
      <p class="muted">{error}</p>
    </div>
  {:else}
    <article class="prose" bind:this={container}>
      <!-- Trusted in-repo audit markdown; see markdown.ts (no untrusted input). -->
      {@html html}
    </article>
  {/if}
</div>

<style>
  .docbar {
    display: flex;
    align-items: baseline;
    gap: 10px;
    padding-bottom: 12px;
    margin-bottom: 8px;
    border-bottom: 1px solid var(--border);
  }
  .filename {
    font-size: 12.5px;
    color: var(--text-2);
    font-weight: 600;
  }
  .err {
    padding: 16px 18px;
  }
  .prose {
    max-width: 920px;
  }
</style>
