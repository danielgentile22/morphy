<script lang="ts">
  // History sub-page (UI overhaul P3 / #112) — the activity stream as a
  // chronological feed, filterable by lead / member / channel. Reads the same
  // /api/activity model the Calendar does.
  import { onMount } from 'svelte';
  import { activity, type ActivityEvent } from '../lib/activity-store.svelte';
  import { tasks } from '../lib/tasks-store.svelte';
  import { leadHash } from '../lib/nav';

  // Suppressed (heading={false}) when embedded in the single scrolling
  // Dashboard, which supplies one uniform section heading (PRD #125). Default
  // true keeps the standalone render self-titled.
  let { heading = true }: { heading?: boolean } = $props();

  onMount(() => {
    void activity.load();
    void tasks.loadUsers(); // member filter options
  });

  const KIND_ICON: Record<ActivityEvent['kind'], string> = {
    touch: '→',
    reply: '↩',
    status: '◇',
    flag: '⚑',
  };
  const KIND_LABEL: Record<ActivityEvent['kind'], string> = {
    touch: 'Touch',
    reply: 'Reply',
    status: 'Status',
    flag: 'Flag',
  };
  // Channel filter options come from the store's accumulated vocabulary (union
  // of channels ever seen), not the currently-filtered events — otherwise the
  // options collapse to just the selected channel after a pick (#112 fix).
  const channels = $derived(activity.channelVocab);
</script>

<div class="history" data-testid="history">
  <header class="head">
    {#if heading}<h2>History</h2>{/if}
    <span class="sub">Everything done — the full activity log.</span>
  </header>

  <div class="filterbar" data-testid="history-filter">
    <select
      aria-label="Channel"
      value={activity.filter.channel}
      onchange={(e) => activity.setFilter({ channel: e.currentTarget.value })}
    >
      <option value="">any channel</option>
      {#each channels as c (c)}<option value={c}>{c}</option>{/each}
    </select>
    <select
      aria-label="Member"
      value={activity.filter.member == null ? '' : String(activity.filter.member)}
      onchange={(e) => activity.setFilter({ member: e.currentTarget.value ? Number(e.currentTarget.value) : null })}
    >
      <option value="">any member</option>
      {#each tasks.users as u (u.id)}<option value={String(u.id)}>{u.name}</option>{/each}
    </select>
    <input
      type="date"
      aria-label="From"
      value={activity.filter.dateFrom}
      onchange={(e) => activity.setFilter({ dateFrom: e.currentTarget.value })}
    />
    <input
      type="date"
      aria-label="To"
      value={activity.filter.dateTo}
      onchange={(e) => activity.setFilter({ dateTo: e.currentTarget.value })}
    />
    <button class="clear" onclick={() => activity.resetFilter()}>Clear</button>
  </div>

  {#if activity.status === 'loading'}
    <p class="muted">Loading…</p>
  {:else if activity.events.length === 0}
    <p class="muted" data-testid="history-empty">No activity matches.</p>
  {:else}
    <ul class="feed" data-testid="history-feed">
      {#each activity.events as e (e.id)}
        <li class="evt" data-kind={e.kind}>
          <span class="when">{e.date}</span>
          <span class="kind kind-{e.kind}">{KIND_ICON[e.kind]}</span>
          <a class="owner" href={leadHash(e.cluster_id)} title={e.owner_name || e.cluster_id}>{e.owner_name || e.cluster_id}</a>
          <span class="what">{KIND_LABEL[e.kind]}{e.channel && e.kind !== 'status' && e.kind !== 'flag' ? ` · ${e.channel}` : ''}</span>
          <span class="summary">{e.summary}</span>
          {#if e.member_name}<span class="member">{e.member_name}</span>{/if}
        </li>
      {/each}
    </ul>
  {/if}
</div>

<style>
  /* No width cap — fills the dashboard column (.dash-inner). */
  .head {
    display: flex;
    align-items: baseline;
    gap: 10px;
    margin-bottom: 12px;
  }
  h2 {
    font-size: 18px;
  }
  .sub {
    font-size: 12.5px;
    color: var(--muted);
  }
  .filterbar {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    align-items: center;
    margin-bottom: 12px;
  }
  .filterbar select,
  .filterbar input {
    font: inherit;
    font-size: 12px;
    padding: 5px 8px;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius);
    background: var(--panel);
  }
  .clear {
    background: none;
    border: none;
    color: var(--accent);
    font-size: 12px;
    cursor: pointer;
  }
  .muted {
    color: var(--muted);
    font-size: 13px;
  }
  .feed {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  /* Fixed column tracks so the icon / kind label / value line up vertically
     regardless of the owner name's length. Owner is a fixed track and
     truncates (full name on hover); the value flexes to fill the rest. */
  .evt {
    display: grid;
    grid-template-columns: 86px 22px 16rem 7em 1fr auto;
    align-items: baseline;
    gap: 10px;
    padding: 7px 2px;
    border-bottom: 1px solid var(--border);
    font-size: 12.5px;
  }
  .when {
    color: var(--muted);
    font-variant-numeric: tabular-nums;
  }
  .kind {
    text-align: center;
    color: var(--text-2);
  }
  .kind-reply {
    color: var(--accent);
    font-weight: 700;
  }
  .kind-flag {
    color: var(--color-warning);
  }
  .owner {
    color: var(--text);
    font-weight: 600;
    text-decoration: none;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .owner:hover {
    text-decoration: underline;
  }
  .what {
    color: var(--text-2);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .summary {
    color: var(--muted);
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .member {
    font-size: 11px;
    color: var(--muted);
    background: var(--panel-2);
    border-radius: 999px;
    padding: 1px 8px;
  }
</style>
