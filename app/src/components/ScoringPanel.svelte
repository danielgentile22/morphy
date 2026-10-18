<script lang="ts">
  // Scoring weights panel (UI overhaul P4 / #114) — tune the feature weights;
  // Explore re-ranks live. "Default" ranks by the baked interestingness (no
  // regression); touching any slider switches to a custom blend. (#115 adds
  // named presets here.)
  import { onMount } from 'svelte';
  import { scoring } from '../lib/scoring-store.svelte';
  import { auth } from '../lib/auth-store.svelte';
  import { SCORE_FEATURES, type ScoreWeights } from '../lib/scoring';

  let newName = $state('');
  // Collapsed by default — it's a power-user panel, not something you want
  // taking over the sidebar on every load. The header shows the active mode
  // so you can tell at a glance whether a custom blend is in effect.
  let collapsed = $state(true);

  onMount(() => {
    void scoring.loadPresets();
  });

  // ── debounced weight commits (PERF-003) ────────────────────────────────
  // Each weight tick rebuilt the 16k-entry score map AND re-sorted the 80k-row
  // Explore set + the Leads/MyLeads worklists. Keep the thumb responsive via a
  // local mirror and debounce the commit (one batched setWeights at the end).
  const SCORING_DEBOUNCE_MS = 140;
  let localWeights = $state<ScoreWeights>({ ...scoring.weights });
  // Re-sync when the store's weights change elsewhere (preset apply, reset).
  $effect(() => void (localWeights = { ...scoring.weights }));

  let weightTimer: ReturnType<typeof setTimeout> | null = null;
  let pendingWeights: Partial<ScoreWeights> = {};
  function onWeightInput(key: keyof ScoreWeights, value: number): void {
    localWeights = { ...localWeights, [key]: value };
    pendingWeights = { ...pendingWeights, [key]: value };
    if (weightTimer) clearTimeout(weightTimer);
    weightTimer = setTimeout(flushWeights, SCORING_DEBOUNCE_MS);
  }
  function flushWeights(): void {
    if (weightTimer) {
      clearTimeout(weightTimer);
      weightTimer = null;
    }
    if (Object.keys(pendingWeights).length === 0) return;
    scoring.setWeights(pendingWeights);
    pendingWeights = {};
  }
  function cancelWeights(): void {
    if (weightTimer) {
      clearTimeout(weightTimer);
      weightTimer = null;
    }
    pendingWeights = {};
  }
  // Flush an in-flight drag before the panel unmounts (sidebar collapse).
  $effect(() => () => flushWeights());

  function resetScoring(): void {
    cancelWeights();
    scoring.reset();
  }

  async function save(): Promise<void> {
    const ok = await scoring.save(newName.trim());
    if (ok) newName = '';
  }
  function onPickPreset(e: Event): void {
    cancelWeights(); // a queued slider commit must not clobber the picked preset
    const v = (e.currentTarget as HTMLSelectElement).value;
    if (v === '') scoring.reset();
    else {
      const p = scoring.presets.find((x) => x.id === Number(v));
      if (p) scoring.apply(p);
    }
  }
</script>

<section class="scoring" data-testid="scoring-panel">
  <button
    type="button"
    class="sp-head"
    data-testid="scoring-toggle"
    aria-expanded={!collapsed}
    onclick={() => (collapsed = !collapsed)}
  >
    <span class="chev" class:open={!collapsed} aria-hidden="true">▸</span>
    <span class="title">Scoring</span>
    <span class="mode" data-testid="scoring-mode">
      {scoring.useDefault ? 'Default (interestingness)' : 'Custom'}
    </span>
  </button>
  {#if !collapsed}
    <!-- Named presets (#115, tenant-shared). -->
    <div class="presets">
    <select
      class="preset-pick"
      data-testid="preset-select"
      aria-label="Scoring preset"
      value={scoring.activePresetId == null ? '' : String(scoring.activePresetId)}
      onchange={onPickPreset}
    >
      <option value="">Default (interestingness)</option>
      {#each scoring.presets as p (p.id)}
        <option value={String(p.id)}>{p.name}{p.is_default ? ' ★' : ''}</option>
      {/each}
    </select>
    {#if scoring.activePresetId != null && !auth.readOnly}
      <button class="mini" data-testid="preset-default" onclick={() => scoring.setDefault(scoring.activePresetId!)}>set default</button>
      <button class="mini" data-testid="preset-delete" onclick={() => scoring.remove(scoring.activePresetId!)}>delete</button>
    {/if}
  </div>
  {#if !scoring.useDefault}
    {#if !auth.readOnly}
    <div class="saverow">
      <input
        class="pname"
        data-testid="preset-name"
        bind:value={newName}
        placeholder="Save current as…"
        aria-label="New preset name"
      />
      <button class="mini save" data-testid="preset-save" onclick={save} disabled={!newName.trim()}>
        Save
      </button>
    </div>
    {/if}
    <button class="reset" data-testid="scoring-reset" onclick={resetScoring}>
      ↺ Reset to default
    </button>
  {/if}
  {#if scoring.presetError}<p class="perr">{scoring.presetError}</p>{/if}
  <div class="weights">
    {#each SCORE_FEATURES as f (f.key)}
      <label class="w">
        <span class="wlabel">{f.label}</span>
        <input
          type="range"
          min="0"
          max="1"
          step="0.05"
          data-testid="weight-{f.key}"
          value={localWeights[f.key as keyof ScoreWeights]}
          oninput={(e) => onWeightInput(f.key as keyof ScoreWeights, Number(e.currentTarget.value))}
        />
        <span class="wval">{localWeights[f.key as keyof ScoreWeights].toFixed(2)}</span>
      </label>
    {/each}
  </div>
    <p class="hint">
      {scoring.useDefault
        ? 'Towers rank by the baked interestingness. Drag a slider to customize.'
        : 'Explore re-ranks live by these weights.'}
    </p>
  {/if}
</section>

<style>
  .scoring {
    padding: 14px 18px;
    border-bottom: 1px solid var(--border);
  }
  .sp-head {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
    padding: 0;
    background: none;
    border: none;
    font: inherit;
    text-align: left;
    cursor: pointer;
  }
  .chev {
    font-size: 10px;
    color: var(--muted);
    transition: transform 0.12s ease;
  }
  .chev.open {
    transform: rotate(90deg);
  }
  .title {
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
  }
  .mode {
    margin-left: auto;
    font-size: 10.5px;
    color: var(--accent);
  }
  .reset {
    background: none;
    border: none;
    color: var(--accent);
    font-size: 11.5px;
    padding: 2px 0 6px;
    cursor: pointer;
  }
  .presets {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-top: 8px;
  }
  .preset-pick {
    flex: 1;
    font: inherit;
    font-size: 12px;
    padding: 4px 6px;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius);
    background: var(--panel);
  }
  .saverow {
    display: flex;
    gap: 6px;
    margin-top: 6px;
  }
  .pname {
    flex: 1;
    font: inherit;
    font-size: 12px;
    padding: 4px 7px;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius);
    background: var(--panel);
  }
  .mini {
    background: var(--panel);
    border: 1px solid var(--border-strong);
    border-radius: var(--radius);
    font-size: 11px;
    padding: 3px 8px;
    color: var(--text-2);
    cursor: pointer;
  }
  .mini.save {
    border-color: var(--accent);
    color: var(--accent);
  }
  .perr {
    color: var(--danger);
    font-size: 11px;
    margin-top: 4px;
  }
  .weights {
    display: flex;
    flex-direction: column;
    gap: 5px;
    margin-top: 6px;
  }
  .w {
    display: grid;
    grid-template-columns: 1fr 90px 30px;
    align-items: center;
    gap: 8px;
    font-size: 11.5px;
  }
  .wlabel {
    color: var(--text-2);
  }
  .wval {
    text-align: right;
    color: var(--muted);
    font-variant-numeric: tabular-nums;
  }
  input[type='range'] {
    width: 100%;
  }
  .hint {
    margin-top: 8px;
    font-size: 11px;
    color: var(--muted);
  }
</style>
