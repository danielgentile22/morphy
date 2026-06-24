<script lang="ts">
  import { onMount, tick } from 'svelte';
  import { askClaude } from '../lib/ask-claude.svelte';

  // The textarea, focused on open and submitted on Enter (Shift+Enter = newline).
  let input = $state<HTMLTextAreaElement | null>(null);
  let scroller = $state<HTMLDivElement | null>(null);

  // The inline "Ask Claude" bubble that floats at a text selection (#189):
  // viewport coords + the selected text, or null when nothing is offered.
  let bubble = $state<{ x: number; y: number; text: string } | null>(null);

  // Coarse pointer (phone/tablet): render the affordance as a fixed bar the OS's
  // own selection menu can't cover, rather than a bubble floating at the
  // selection (which the native Copy/Look-Up bar sits right on top of).
  let coarse = $state(false);

  // Focus the input when the panel opens; keep the transcript pinned to the
  // newest text as it streams in.
  $effect(() => {
    if (askClaude.open) {
      void tick().then(() => input?.focus());
    }
  });
  $effect(() => {
    // Re-runs as messages/streaming change — scroll the latest into view.
    void askClaude.messages;
    void askClaude.streaming;
    if (scroller) scroller.scrollTop = scroller.scrollHeight;
  });

  // Selection-bubble wiring. `selectionchange` covers both desktop drag and
  // native mobile selection; a scroll (anywhere, capture phase) dismisses it.
  onMount(() => {
    const mq = matchMedia('(pointer: coarse)');
    coarse = mq.matches;
    const onPointerKind = (e: MediaQueryListEvent): void => {
      coarse = e.matches;
    };
    // The floating bubble goes stale when the page scrolls, so dismiss it — but
    // only for a fine pointer. On touch the affordance is a fixed bar and the
    // OS selection rides along with the content, so scrolling must not clear it.
    const onScroll = (): void => {
      if (!coarse) bubble = null;
    };
    mq.addEventListener('change', onPointerKind);
    document.addEventListener('selectionchange', updateBubble);
    window.addEventListener('scroll', onScroll, true);
    return () => {
      mq.removeEventListener('change', onPointerKind);
      document.removeEventListener('selectionchange', updateBubble);
      window.removeEventListener('scroll', onScroll, true);
    };
  });

  function updateBubble(): void {
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed || sel.rangeCount === 0) {
      bubble = null;
      return;
    }
    const text = sel.toString().trim();
    if (!text) {
      bubble = null;
      return;
    }
    // Don't offer to ask about Claude's own answer or the Ask Claude UI itself.
    // Match the dialog by its OWN class (.ask-panel) — `.panel` is a generic
    // content-card class the catalog reuses (e.g. a Data Catalog group), so
    // excluding `.panel` would wrongly suppress the bubble across the catalog.
    const node = sel.anchorNode;
    const el = node instanceof Element ? node : (node?.parentElement ?? null);
    if (el?.closest('.ask-panel, .ask-bubble, .launcher')) {
      bubble = null;
      return;
    }
    const rect = sel.getRangeAt(0).getBoundingClientRect();
    if (rect.width === 0 && rect.height === 0) {
      bubble = null;
      return;
    }
    bubble = { x: rect.left + rect.width / 2, y: rect.top, text };
  }

  function askSelection(): void {
    if (!bubble) return;
    askClaude.askAboutSelection(bubble.text);
    bubble = null;
  }

  function onKeydown(e: KeyboardEvent): void {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void askClaude.send();
    }
  }

  function onPanelKeydown(e: KeyboardEvent): void {
    if (e.key === 'Escape') askClaude.close();
  }
</script>

<!-- The inline selection affordance (#189): a bubble floating at the highlighted
     text on desktop, or a fixed bottom bar on touch (where the OS's own
     selection menu would cover a floating bubble). mousedown is prevented so a
     desktop click doesn't collapse the selection before it lands; the selected
     text is captured in `bubble.text`, so a touch tap still works even if it
     collapses the selection. -->
{#if bubble}
  <button
    class="ask-bubble"
    class:is-bar={coarse}
    style={coarse ? '' : `left: ${bubble.x}px; top: ${bubble.y}px;`}
    onmousedown={(e) => e.preventDefault()}
    onclick={askSelection}
  >
    <span aria-hidden="true">✨</span> Ask Claude{coarse ? ' about this' : ''}
  </button>
{/if}

<!-- Persistent corner button — always available, on every catalog view. -->
<button
  class="launcher"
  class:hidden={askClaude.open}
  onclick={() => askClaude.openPanel()}
  aria-label="Ask Claude about this catalog"
  aria-expanded={askClaude.open}
>
  <span aria-hidden="true">✨</span> Ask Claude
</button>

{#if askClaude.open}
  <div
    class="ask-panel"
    role="dialog"
    aria-label="Ask Claude"
    aria-modal="false"
    onkeydown={onPanelKeydown}
    tabindex="-1"
  >
    <header class="head">
      <h2><span aria-hidden="true">✨</span> Ask Claude</h2>
      <button class="close" onclick={() => askClaude.close()} aria-label="Close Ask Claude">✕</button>
    </header>

    <div class="messages" bind:this={scroller}>
      {#if askClaude.messages.length === 0}
        <p class="hint">
          Ask anything about this data catalog — what a rating means, where a
          signal comes from, or why a row is trusted the way it is. Or highlight
          any text on the page and ask about that.
        </p>
      {/if}
      {#each askClaude.messages as msg, i (i)}
        {#if msg.role === 'user'}
          <div class="msg user">{msg.content}</div>
        {:else}
          <div class="msg assistant">
            {#if msg.content}
              <!-- eslint-disable-next-line svelte/no-at-html-tags -->
              {@html askClaude.render(msg.content)}
            {:else if askClaude.streaming}
              <span class="typing" aria-label="Claude is typing">●●●</span>
            {/if}
          </div>
        {/if}
      {/each}
      {#if askClaude.error}
        <p class="err" role="alert">{askClaude.error}</p>
      {/if}
    </div>

    {#if askClaude.selection}
      <!-- The selection the conversation is scoped to (#189). Clearing it drops
           back to a free-typed question without losing the thread. -->
      <div class="sel-chip">
        <span class="sel-label">Asking about</span>
        <span class="sel-text">“{askClaude.selection}”</span>
        <button class="sel-clear" onclick={() => askClaude.clearSelection()} aria-label="Clear selection"
          >✕</button
        >
      </div>
    {/if}

    <form
      class="composer"
      onsubmit={(e) => {
        e.preventDefault();
        void askClaude.send();
      }}
    >
      <textarea
        bind:this={input}
        bind:value={askClaude.question}
        onkeydown={onKeydown}
        placeholder={askClaude.selection ? 'Ask about the selected text…' : 'Ask a question…'}
        rows="2"
        aria-label="Your question"
      ></textarea>
      <button
        type="submit"
        class="send"
        disabled={askClaude.streaming ||
          (askClaude.question.trim().length === 0 && !askClaude.selection)}
      >
        {askClaude.streaming ? '…' : 'Send'}
      </button>
    </form>
  </div>
{/if}

<style>
  .launcher {
    position: fixed;
    right: 18px;
    bottom: 18px;
    z-index: 80;
    display: inline-flex;
    align-items: center;
    gap: 7px;
    padding: 10px 16px;
    border: 1px solid var(--accent-soft);
    background: var(--accent);
    color: #fff;
    border-radius: 999px;
    font-weight: 600;
    font-size: 14px;
    box-shadow: var(--shadow-lg);
    cursor: pointer;
  }
  .launcher:hover {
    filter: brightness(1.06);
  }
  .launcher.hidden {
    display: none;
  }

  /* The inline selection bubble — fixed at the selection rect, centered above it. */
  .ask-bubble {
    position: fixed;
    z-index: 95;
    transform: translate(-50%, calc(-100% - 8px));
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 6px 11px;
    border: 1px solid var(--accent-soft);
    background: var(--accent);
    color: #fff;
    border-radius: 999px;
    font-weight: 600;
    font-size: 12.5px;
    white-space: nowrap;
    box-shadow: var(--shadow-lg);
    cursor: pointer;
  }
  .ask-bubble:hover {
    filter: brightness(1.06);
  }
  /* Touch: a fixed, thumb-reachable bar instead of a bubble pinned to the
     selection. The OS selection menu sits at the top of the selection; ours
     sits at the bottom of the screen, so it's never hidden behind it. */
  .ask-bubble.is-bar {
    left: 50%;
    top: auto;
    bottom: calc(76px + env(safe-area-inset-bottom, 0px));
    transform: translateX(-50%);
    padding: 12px 20px;
    font-size: 14.5px;
  }

  .ask-panel {
    position: fixed;
    right: 0;
    top: 0;
    bottom: 0;
    z-index: 90;
    width: min(420px, 100vw);
    display: flex;
    flex-direction: column;
    background: var(--panel);
    border-left: 1px solid var(--border);
    box-shadow: var(--shadow-lg);
  }
  .head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 16px;
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
  }
  .head h2 {
    margin: 0;
    font-size: 15px;
    font-weight: 700;
    letter-spacing: -0.01em;
  }
  .close {
    width: 30px;
    height: 30px;
    border: 1px solid var(--border);
    background: var(--panel);
    color: var(--text-2);
    border-radius: var(--radius-sm);
    cursor: pointer;
    font-size: 13px;
  }
  .close:hover {
    background: var(--panel-2);
  }

  .messages {
    flex: 1 1 auto;
    overflow-y: auto;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .hint {
    color: var(--text-2);
    font-size: 13.5px;
    line-height: 1.5;
    margin: 4px 0;
  }
  .msg {
    font-size: 14px;
    line-height: 1.55;
    border-radius: var(--radius);
    padding: 10px 13px;
    max-width: 92%;
    overflow-wrap: anywhere;
  }
  .msg.user {
    align-self: flex-end;
    background: var(--accent-bg);
    color: var(--text);
    border: 1px solid var(--accent-soft);
    white-space: pre-wrap;
  }
  .msg.assistant {
    align-self: flex-start;
    background: var(--panel-2);
    color: var(--text);
    border: 1px solid var(--border);
  }
  /* Markdown emitted by renderAnswer — tighten default block spacing. */
  .msg.assistant :global(p) {
    margin: 0 0 8px;
  }
  .msg.assistant :global(p:last-child) {
    margin-bottom: 0;
  }
  .msg.assistant :global(ul),
  .msg.assistant :global(ol) {
    margin: 0 0 8px;
    padding-left: 20px;
  }
  .msg.assistant :global(code) {
    font-family: var(--mono);
    font-size: 0.88em;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 0 4px;
  }
  .msg.assistant :global(pre) {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 10px;
    overflow-x: auto;
  }
  .typing {
    color: var(--text-2);
    letter-spacing: 2px;
    font-size: 11px;
  }
  .err {
    color: var(--danger);
    font-size: 13px;
    margin: 0;
  }

  /* The selection-scope chip above the composer (#189). */
  .sel-chip {
    display: flex;
    align-items: baseline;
    gap: 6px;
    margin: 0 16px;
    padding: 7px 10px;
    background: var(--accent-bg);
    border: 1px solid var(--accent-soft);
    border-radius: var(--radius-sm);
    font-size: 12.5px;
    flex-shrink: 0;
  }
  .sel-label {
    color: var(--text-2);
    font-weight: 600;
    flex-shrink: 0;
  }
  .sel-text {
    color: var(--text);
    flex: 1 1 auto;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .sel-clear {
    flex-shrink: 0;
    border: none;
    background: transparent;
    color: var(--text-2);
    cursor: pointer;
    font-size: 12px;
    padding: 0 2px;
    line-height: 1;
  }
  .sel-clear:hover {
    color: var(--text);
  }

  .composer {
    display: flex;
    gap: 8px;
    padding: 12px 16px;
    border-top: 1px solid var(--border);
    flex-shrink: 0;
  }
  .composer textarea {
    flex: 1 1 auto;
    resize: none;
    font: inherit;
    font-size: 14px;
    padding: 8px 10px;
    color: var(--text);
    background: var(--panel-2);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
  }
  .composer textarea:focus {
    outline: 2px solid var(--accent);
    outline-offset: -1px;
  }
  .send {
    align-self: flex-end;
    padding: 8px 16px;
    border: 1px solid var(--accent-soft);
    background: var(--accent);
    color: #fff;
    border-radius: var(--radius-sm);
    font-weight: 600;
    cursor: pointer;
  }
  .send:disabled {
    opacity: 0.5;
    cursor: default;
  }

  @media (max-width: 480px) {
    .ask-panel {
      width: 100vw;
    }
  }
</style>
