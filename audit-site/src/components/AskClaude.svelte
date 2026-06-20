<script lang="ts">
  import { tick } from 'svelte';
  import { askClaude } from '../lib/ask-claude.svelte';

  // The textarea, focused on open and submitted on Enter (Shift+Enter = newline).
  let input = $state<HTMLTextAreaElement | null>(null);
  let scroller = $state<HTMLDivElement | null>(null);

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
    class="panel"
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
          signal comes from, or why a row is trusted the way it is.
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
        placeholder="Ask a question…"
        rows="2"
        aria-label="Your question"
      ></textarea>
      <button
        type="submit"
        class="send"
        disabled={askClaude.streaming || askClaude.question.trim().length === 0}
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

  .panel {
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
    color: #b00020;
    font-size: 13px;
    margin: 0;
  }
  :global(.dark) .err {
    color: #ff8a8a;
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
    .panel {
      width: 100vw;
    }
  }
</style>
