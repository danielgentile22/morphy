<script lang="ts">
  import { notice } from '../lib/notice.svelte';
</script>

{#if notice.message}
  <div class="notice" role="status" aria-live="polite" data-testid="notice">
    <span>{notice.message}</span>
    <button class="btn btn-tertiary btn-sm" type="button" onclick={() => notice.dismiss()}>
      Dismiss
    </button>
  </div>
{/if}

<style>
  .notice {
    position: fixed;
    left: 50%;
    bottom: 24px;
    transform: translateX(-50%);
    z-index: 1000;
    display: flex;
    align-items: center;
    gap: 12px;
    max-width: min(520px, calc(100vw - 32px));
    padding: 10px 12px 10px 16px;
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-md);
    background: var(--color-elevated);
    color: var(--color-text-primary);
    font-size: var(--text-body-sm-size);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
  }
</style>
