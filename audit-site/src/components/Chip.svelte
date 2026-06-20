<script lang="ts">
  import { tagMeta, DIMENSION_LABELS } from '../lib/tags';

  let { dimension, value, sm = false }: { dimension: string; value: string; sm?: boolean } = $props();

  const meta = $derived(tagMeta(dimension, value));
  // What axis this chip encodes ("what is being shown") — the popover's headline.
  const dimLabel = $derived(DIMENSION_LABELS[dimension] ?? dimension);
  // The full sentence as the button's accessible name, so a screen-reader user
  // hears the meaning the sighted popover shows.
  const aria = $derived(`${dimLabel}: ${meta.label} — ${meta.title}`);
</script>

<!-- A focusable chip: the value stays compact, but hover / focus / tap reveals a
     popover naming the dimension + what the value means (PRD #178 — the tags are
     otherwise opaque vocab). The button has no action; it's an info disclosure. -->
<span class="chip-wrap">
  <button type="button" class="chip chip--{meta.tone} tagchip" class:chip--sm={sm} aria-label={aria}>
    {meta.label}
  </button>
  <span class="pop" role="tooltip" aria-hidden="true">
    <span class="pop-dim">{dimLabel}</span>
    <span class="pop-mean"><strong>{meta.label}</strong> — {meta.title}</span>
  </span>
</span>

<style>
  .chip-wrap {
    position: relative;
    display: inline-flex;
  }
  /* Reset the native button look — the global .chip / .chip--<tone> classes
     supply the visual; we only fix the inherited font + signal interactivity. */
  .tagchip {
    font-family: inherit;
    letter-spacing: inherit;
    cursor: help;
  }
  .tagchip:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 1px;
  }

  /* The popover: above the chip so the section's `overflow:hidden` (the
     collapsible group) never clips it; the tags always have content above. */
  .pop {
    position: absolute;
    left: 0;
    bottom: calc(100% + 6px);
    z-index: 60;
    width: max-content;
    max-width: 240px;
    display: flex;
    flex-direction: column;
    gap: 3px;
    padding: 8px 10px;
    text-align: left;
    white-space: normal;
    background: var(--panel);
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-sm);
    box-shadow: var(--shadow);
    font-size: 11.5px;
    font-weight: 400;
    line-height: 1.45;
    color: var(--text-2);
    opacity: 0;
    visibility: hidden;
    transform: translateY(3px);
    transition:
      opacity 0.12s ease,
      transform 0.12s ease,
      visibility 0.12s;
    pointer-events: none;
  }
  .chip-wrap:hover > .pop,
  .chip-wrap:focus-within > .pop {
    opacity: 1;
    visibility: visible;
    transform: translateY(0);
  }
  .pop-dim {
    font-weight: 700;
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--text);
  }
  .pop strong {
    color: var(--text);
    font-weight: 600;
  }
</style>
