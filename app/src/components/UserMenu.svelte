<script lang="ts">
  // The top-nav user menu (PRD #121): the `email · team` label becomes a
  // dropdown holding Settings + Sign out, so account actions are grouped and the
  // primary nav tabs stay uncluttered.
  import { auth } from '../lib/auth-store.svelte';
  import { settingsHash } from '../lib/nav';

  let open = $state(false);
  let root = $state<HTMLDivElement>();

  function openSettings(): void {
    location.hash = settingsHash();
    open = false;
  }
  function signOut(): void {
    open = false;
    auth.signOut();
  }

  // Close on outside click / Escape while open. Registered only while open so
  // it costs nothing otherwise; capture phase so it sees clicks anywhere.
  $effect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent): void => {
      if (e.target instanceof Node && root && !root.contains(e.target)) open = false;
    };
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') open = false;
    };
    window.addEventListener('click', onClick, true);
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('click', onClick, true);
      window.removeEventListener('keydown', onKey);
    };
  });
</script>

<div class="usermenu" bind:this={root}>
  <button
    class="trigger"
    data-testid="user-menu"
    aria-haspopup="menu"
    aria-expanded={open}
    onclick={() => (open = !open)}
  >
    <span class="who" data-testid="nav-user">{auth.name}{auth.team ? ` · ${auth.team}` : ''}</span>
    <span class="caret" aria-hidden="true">▾</span>
  </button>
  {#if open}
    <div class="menu" role="menu" data-testid="user-menu-popup">
      <button class="item" role="menuitem" data-testid="menu-settings" onclick={openSettings}>
        ⚙ Settings
      </button>
      <button class="item" role="menuitem" data-testid="signout" onclick={signOut}>
        ⏻ Sign out
      </button>
    </div>
  {/if}
</div>

<style>
  .usermenu {
    margin-left: auto;
    position: relative;
  }
  .trigger {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    background: none;
    border: 1px solid transparent;
    border-radius: var(--radius);
    padding: 4px 8px;
    font: inherit;
    font-size: 12px;
    color: var(--text-2);
    cursor: pointer;
  }
  .trigger:hover {
    border-color: var(--border);
    background: var(--panel-2);
  }
  .caret {
    font-size: 9px;
    color: var(--muted);
  }
  .menu {
    position: absolute;
    right: 0;
    top: calc(100% + 4px);
    min-width: 160px;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    box-shadow: var(--shadow-lg);
    padding: 4px;
    z-index: 50;
    display: flex;
    flex-direction: column;
  }
  .item {
    text-align: left;
    background: none;
    border: none;
    border-radius: var(--radius);
    padding: 7px 10px;
    font: inherit;
    font-size: 12.5px;
    color: var(--text);
    cursor: pointer;
  }
  .item:hover {
    background: var(--panel-2);
  }
</style>
