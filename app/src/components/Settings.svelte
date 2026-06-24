<script lang="ts">
  // The per-user Settings page (PRD #121). One `#/settings` route; the four
  // sections are local component state (no per-section deep links). Renders as
  // an opaque surface over the still-mounted Explore map, like the other
  // non-Explore sections.
  import { SECTION_HASH } from '../lib/nav';
  import SettingsAccount from './SettingsAccount.svelte';
  import SettingsAppearance from './SettingsAppearance.svelte';
  import SettingsFilters from './SettingsFilters.svelte';
  import SettingsAutomations from './SettingsAutomations.svelte';

  type SectionKey = 'account' | 'display' | 'filters' | 'automations';
  const SECTIONS: { key: SectionKey; label: string }[] = [
    { key: 'account', label: 'Account' },
    { key: 'display', label: 'Map & display' },
    { key: 'filters', label: 'Filter defaults' },
    { key: 'automations', label: 'Automations' },
  ];
  let active = $state<SectionKey>('account');
</script>

<div class="settings" data-testid="settings">
  <header class="head">
    <h1>Settings</h1>
    <button class="btn btn-secondary btn-sm" data-testid="settings-done" onclick={() => (location.hash = SECTION_HASH.dashboard)}>
      Done
    </button>
  </header>
  <div class="body">
    <nav class="rail" aria-label="Settings sections">
      {#each SECTIONS as s (s.key)}
        <button
          class="rail-item"
          class:on={active === s.key}
          data-testid={`settings-rail-${s.key}`}
          onclick={() => (active = s.key)}
        >
          {s.label}
        </button>
      {/each}
    </nav>
    <div class="content">
      {#if active === 'account'}
        <SettingsAccount />
      {:else if active === 'display'}
        <SettingsAppearance />
      {:else if active === 'filters'}
        <SettingsFilters />
      {:else}
        <SettingsAutomations />
      {/if}
    </div>
  </div>
</div>

<style>
  .settings {
    height: 100%;
    display: flex;
    flex-direction: column;
    background: var(--bg);
  }
  .head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 24px;
    border-bottom: 1px solid var(--border);
  }
  .head h1 {
    font-size: 18px;
  }
  .body {
    flex: 1;
    display: flex;
    min-height: 0;
  }
  .rail {
    width: 200px;
    flex-shrink: 0;
    border-right: 1px solid var(--border);
    padding: 12px 8px;
    display: flex;
    flex-direction: column;
    gap: 2px;
    background: var(--panel);
  }
  .rail-item {
    text-align: left;
    background: none;
    border: none;
    border-radius: var(--radius);
    padding: 9px 12px;
    font: inherit;
    font-size: 13px;
    color: var(--text-2);
    cursor: pointer;
  }
  .rail-item:hover {
    background: var(--panel-2);
  }
  .rail-item.on {
    background: var(--accent-soft);
    color: var(--accent);
    font-weight: 600;
  }
  .content {
    flex: 1;
    overflow-y: auto;
    padding: 24px;
  }
</style>
