<script lang="ts">
  // Settings → Map & display (PRD #121): theme, colorblind mode, basemap, and
  // the default map view. All per-user prefs persisted in the backend store; the
  // appearance ones apply live through the user-settings store.
  import { userSettings } from '../lib/user-settings-store.svelte';
  import { readLastView } from '../lib/map-view-cache';
  import type { BasemapName } from '../lib/basemap';

  const s = $derived(userSettings.settings);

  const BASEMAPS: { value: BasemapName; label: string }[] = [
    { value: 'light', label: 'Light (Positron)' },
    { value: 'voyager', label: 'Voyager' },
    { value: 'dark', label: 'Dark Matter' },
  ];

  let homeStatus = $state<'idle' | 'saved' | 'nohome' | 'error'>('idle');

  async function pinHome(): Promise<void> {
    const v = readLastView();
    if (!v) {
      homeStatus = 'nohome';
      return;
    }
    homeStatus = (await userSettings.setHomeView(v)) ? 'saved' : 'error';
  }

  async function clearHome(): Promise<void> {
    homeStatus = (await userSettings.clearHomeView()) ? 'idle' : 'error';
  }
</script>

<section class="set-section" data-testid="settings-display">
  <h2>Map &amp; display</h2>
  <p class="hint">How the app looks and where the map opens — saved to your account.</p>
  {#if userSettings.error}
    <p class="set-status err" data-testid="display-error">Couldn't save: {userSettings.error}</p>
  {/if}

  <div class="set-group">
    <h3>Status colors</h3>
    <label class="set-check">
      <input
        type="checkbox"
        data-testid="colorblind-toggle"
        checked={s.colorblind}
        onchange={(e) => userSettings.save({ colorblind: e.currentTarget.checked })}
      />
      Colorblind-friendly status colors
    </label>
    <p class="hint">Remaps the green/red lead-status pair to a colorblind-safe set with a glyph cue.</p>
  </div>

  <div class="set-group">
    <h3>Basemap</h3>
    <div class="set-row">
      <select
        class="set-select"
        data-testid="basemap-select"
        value={s.basemap}
        onchange={(e) => userSettings.save({ basemap: e.currentTarget.value as BasemapName })}
      >
        {#each BASEMAPS as b (b.value)}
          <option value={b.value}>{b.label}</option>
        {/each}
      </select>
    </div>
    <p class="hint">Dark Matter matches the app; pick Light (Positron) for daylight or field reading.</p>
  </div>

  <div class="set-group">
    <h3>Default map view</h3>
    <div class="set-row">
      <div class="tabs" role="group" aria-label="Default map view">
        <button
          class="tab"
          class:is-active={s.view_mode === 'last'}
          data-testid="view-last"
          onclick={() => userSettings.save({ view_mode: 'last' })}
        >
          Where I left off
        </button>
        <button
          class="tab"
          class:is-active={s.view_mode === 'home'}
          data-testid="view-home"
          onclick={() => userSettings.save({ view_mode: 'home' })}
        >
          Pinned home
        </button>
      </div>
    </div>
    <div class="set-row">
      <button class="btn btn-secondary btn-sm" data-testid="set-home" onclick={pinHome}>
        Set current map view as home
      </button>
      <button
        class="btn btn-secondary btn-sm"
        data-testid="clear-home"
        disabled={!s.home_view}
        onclick={clearHome}
      >
        Clear home
      </button>
      {#if homeStatus === 'saved'}<span class="set-status ok">Home set ✓</span>{/if}
      {#if homeStatus === 'nohome'}<span class="set-status err">Pan/zoom the map first.</span>{/if}
      {#if homeStatus === 'error'}<span class="set-status err">Couldn't save — try again.</span>{/if}
    </div>
    <p class="hint">
      {s.home_view ? 'A home view is pinned.' : 'No home pinned — the map opens where you left off.'}
    </p>
  </div>
</section>
