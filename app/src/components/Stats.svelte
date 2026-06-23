<script lang="ts">
  // Stats sub-page (UI overhaul P3 / #113) — outreach analytics derived from
  // leads + activity: funnel, conversion, reply/win rate, volume by channel;
  // date-range filter; member + state breakdowns. Reads /api/stats.
  import { onMount } from 'svelte';
  import { request, ApiError } from '../lib/leads-api';
  import { tasks } from '../lib/tasks-store.svelte';
  import { auth } from '../lib/auth-store.svelte';
  import type { components } from '../lib/api-types';

  // Suppressed (heading={false}) when embedded in the single scrolling
  // Dashboard, which supplies one uniform section heading (PRD #125); the
  // filter bar stays. Default true keeps the standalone render self-titled.
  let { heading = true }: { heading?: boolean } = $props();

  // Generated from the backend's StatsResponse (PRD #133). `Required<…>`:
  // the by_state/by_member breakdowns default server-side but are always
  // serialized in the response.
  type Stats = Required<components['schemas']['StatsResponse']>;

  let stats = $state<Stats | null>(null);
  let loading = $state(true);
  let filter = $state({ dateFrom: '', dateTo: '', state: '', member: '' });

  async function load(): Promise<void> {
    loading = true;
    const p = new URLSearchParams();
    if (filter.dateFrom) p.set('date_from', filter.dateFrom);
    if (filter.dateTo) p.set('date_to', filter.dateTo);
    if (filter.state) p.set('state', filter.state);
    if (filter.member) p.set('member', filter.member);
    try {
      stats = await request<Stats>(`/stats${p.toString() ? `?${p}` : ''}`);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) auth.signOut();
      stats = null;
    } finally {
      loading = false;
    }
  }

  onMount(() => {
    void load();
    void tasks.loadUsers();
  });

  const FUNNEL_ORDER = ['new', 'researching', 'contacted', 'interested', 'in_business', 'uninterested'];
  const LABEL: Record<string, string> = {
    new: 'New',
    researching: 'Researching',
    contacted: 'Contacted',
    interested: 'Interested',
    in_business: 'In Business',
    uninterested: 'Uninterested',
  };
  function pct(x: number): string {
    return `${Math.round(x * 100)}%`;
  }
</script>

<div class="stats" data-testid="stats">
  <header class="head">
    {#if heading}<h2>Stats</h2>{/if}
    <div class="filterbar" data-testid="stats-filter">
      <input type="date" aria-label="From" bind:value={filter.dateFrom} onchange={load} />
      <input type="date" aria-label="To" bind:value={filter.dateTo} onchange={load} />
      <input class="st" placeholder="state (AR)" aria-label="State" bind:value={filter.state} onchange={load} />
      <select aria-label="Member" bind:value={filter.member} onchange={load}>
        <option value="">all members</option>
        {#each tasks.users as u (u.id)}<option value={String(u.id)}>{u.name}</option>{/each}
      </select>
    </div>
  </header>

  {#if loading}
    <p class="muted">Loading…</p>
  {:else if !stats}
    <p class="muted">Could not load stats.</p>
  {:else}
    {@const s = stats}
    <!-- Halo signature: stat-tiles with a toned top hairline, eyebrow label,
         and a large tabular metric. -->
    <div class="kpis">
      <div class="stat-tile stat-sm" data-tone="info" data-testid="kpi-reply">
        <span class="stat-eyebrow">Reply rate</span>
        <span class="stat-value">{pct(s.reply_rate)}</span>
      </div>
      <div class="stat-tile stat-sm" data-tone="success" data-testid="kpi-win">
        <span class="stat-eyebrow">Win rate</span>
        <span class="stat-value">{pct(s.win_rate)}</span>
      </div>
      <div class="stat-tile stat-sm" data-testid="kpi-activity">
        <span class="stat-eyebrow">Activity events</span>
        <span class="stat-value">{s.activity_total}</span>
      </div>
      <div class="stat-tile stat-sm" data-tone="warning" data-testid="kpi-active-days">
        <span class="stat-eyebrow">Active days</span>
        <span class="stat-value">{s.active_days}</span>
      </div>
    </div>

    <section class="card">
      <h3>Funnel</h3>
      <table class="t" data-testid="funnel">
        <tbody>
          {#each FUNNEL_ORDER as st (st)}
            <tr><td>{LABEL[st]}</td><td class="num">{s.funnel[st] ?? 0}</td></tr>
          {/each}
        </tbody>
      </table>
      <div class="conv">
        {#each Object.entries(s.conversion) as [k, v] (k)}
          <span class="convchip">{k.replace(/_to_/, ' → ').replace(/_/g, ' ')}: <b>{pct(v)}</b></span>
        {/each}
      </div>
    </section>

    <section class="card">
      <h3>Outreach volume by channel</h3>
      {#if Object.keys(s.volume_by_channel).length === 0}
        <p class="muted small">No outbound touches in range.</p>
      {:else}
        <table class="t" data-testid="volume">
          <tbody>
            {#each Object.entries(s.volume_by_channel) as [ch, n] (ch)}
              <tr><td>{ch}</td><td class="num">{n}</td></tr>
            {/each}
          </tbody>
        </table>
      {/if}
    </section>

    <div class="cols">
      <section class="card">
        <h3>By state</h3>
        {#if Object.keys(s.by_state).length === 0}
          <p class="muted small">No leads.</p>
        {:else}
          <table class="t" data-testid="by-state">
            <thead><tr><th>State</th><th>Worked</th><th>Won</th></tr></thead>
            <tbody>
              {#each Object.entries(s.by_state) as [st, f] (st)}
                <tr>
                  <td>{st}</td>
                  <td class="num">{Object.entries(f).filter(([k]) => k !== 'new').reduce((a, [, v]) => a + v, 0)}</td>
                  <td class="num">{f.in_business ?? 0}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        {/if}
      </section>

      <section class="card">
        <h3>By team member (touches)</h3>
        {#if Object.keys(s.by_member).length === 0}
          <p class="muted small">No attributed touches.</p>
        {:else}
          <table class="t" data-testid="by-member">
            <tbody>
              {#each Object.entries(s.by_member) as [m, n] (m)}
                <tr><td>{m}</td><td class="num">{n}</td></tr>
              {/each}
            </tbody>
          </table>
        {/if}
      </section>
    </div>
  {/if}
</div>

<style>
  .stats {
    max-width: 820px;
  }
  .head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 12px;
    flex-wrap: wrap;
    margin-bottom: 14px;
  }
  h2 {
    font-size: 18px;
  }
  .filterbar {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
  }
  .filterbar input,
  .filterbar select {
    font: inherit;
    font-size: 12px;
    padding: 5px 8px;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius);
    background: var(--panel);
  }
  .filterbar .st {
    width: 90px;
  }
  .muted {
    color: var(--muted);
    font-size: 13px;
  }
  .small {
    font-size: 11.5px;
  }
  .kpis {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 12px;
    margin-bottom: 16px;
  }
  .card {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 14px 16px;
    margin-bottom: 14px;
  }
  .card h3 {
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
    margin-bottom: 10px;
  }
  .cols {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 14px;
  }
  @media (max-width: 700px) {
    .cols {
      grid-template-columns: 1fr;
    }
  }
  .t {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
  }
  .t th {
    text-align: left;
    font-size: 11px;
    color: var(--muted);
    padding: 4px 6px;
    border-bottom: 1px solid var(--border);
  }
  .t td {
    padding: 4px 6px;
    border-bottom: 1px solid var(--border);
  }
  .t .num {
    text-align: right;
    font-variant-numeric: tabular-nums;
    font-weight: 600;
  }
  .conv {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 10px;
  }
  .convchip {
    font-size: 11.5px;
    color: var(--text-2);
    background: var(--panel-2);
    border-radius: 999px;
    padding: 2px 10px;
  }
</style>
