<script lang="ts">
  // Settings → Automations (PRD #121): the auto-follow-up rule, relocated here
  // from the Tasks digest. Still a *team-level* setting (the whole team shares
  // one follow-up policy), so it reads/writes the tenant-scoped GET/PUT
  // /api/settings — not the per-user store.
  import { onMount } from 'svelte';
  import { request } from '../lib/leads-api';

  interface Settings {
    auto_followup_enabled: boolean;
    auto_followup_window_days: number;
  }
  let settings = $state<Settings | null>(null);
  let status = $state<'idle' | 'saved' | 'error'>('idle');

  onMount(() => {
    void load();
  });

  async function load(): Promise<void> {
    try {
      settings = await request<Settings>('/settings');
    } catch {
      settings = null;
    }
  }

  async function save(patch: Partial<Settings>): Promise<void> {
    try {
      settings = await request<Settings>('/settings', { method: 'PUT', body: JSON.stringify(patch) });
      status = 'saved';
    } catch {
      status = 'error';
    }
  }
</script>

<section class="set-section" data-testid="settings-automations">
  <h2>Automations</h2>
  <p class="hint">Team-level automation rules — shared by everyone on your team.</p>

  <div class="set-group">
    <h3>Auto follow-up</h3>
    {#if settings}
      <label class="set-check">
        <input
          type="checkbox"
          data-testid="auto-followup-enabled"
          checked={settings.auto_followup_enabled}
          onchange={(e) => save({ auto_followup_enabled: e.currentTarget.checked })}
        />
        Schedule a follow-up task when an owner goes quiet
      </label>
      <div class="set-row" style="margin-top:10px">
        <span class="set-label">After</span>
        <input
          class="set-input"
          style="min-width:80px"
          type="number"
          min="1"
          data-testid="auto-followup-window"
          value={settings.auto_followup_window_days}
          onchange={(e) => save({ auto_followup_window_days: Number(e.currentTarget.value) })}
        />
        <span class="set-label" style="min-width:auto">days of no reply</span>
        {#if status === 'saved'}<span class="set-status ok">Saved ✓</span>{/if}
        {#if status === 'error'}<span class="set-status err">Couldn't save.</span>{/if}
      </div>
    {:else}
      <p class="hint">Loading…</p>
    {/if}
  </div>
</section>
