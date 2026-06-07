<script lang="ts">
  // Dashboard — the landing hub of digests, each expandable to a sub-page
  // (UI overhaul P1 / #104, ADR-065). This slice ships the shell: a digest
  // grid + sub-route scaffold. The digests fill with data in later slices
  // (Attention/Tasks #111, Calendar/History #112, Stats #113).
  import { onMount } from 'svelte';
  import type { DashboardSub } from '../lib/nav';
  import { dashboardHash, leadHash } from '../lib/nav';
  import { dashboard } from '../lib/dashboard-store.svelte';
  import { tasks } from '../lib/tasks-store.svelte';
  import { isTaskInDigest } from '../lib/task-filter';
  import { activity } from '../lib/activity-store.svelte';
  import Tasks from './Tasks.svelte';
  import History from './History.svelte';
  import Calendar from './Calendar.svelte';
  import Stats from './Stats.svelte';

  let { sub }: { sub: DashboardSub } = $props();

  // The digest hub loads the attention feed + tasks for the Tasks digest.
  onMount(() => {
    if (sub === 'home') {
      void dashboard.loadAttention();
      void tasks.load();
      void activity.load(); // for the Calendar digest (last contact / reply)
    }
  });

  const today = new Date().toISOString().slice(0, 10);
  const digestTasks = $derived(tasks.tasks.filter((t) => isTaskInDigest(t, today)));

  interface Digest {
    sub: Exclude<DashboardSub, 'home'>;
    title: string;
    blurb: string;
  }
  const DIGESTS: Digest[] = [
    {
      sub: 'tasks',
      title: 'Tasks',
      blurb: 'Due today/tomorrow + high-priority follow-ups and todos.',
    },
    {
      sub: 'calendar',
      title: 'Calendar',
      blurb: 'Recent + upcoming activity and task due-dates on a time-grid.',
    },
    {
      sub: 'history',
      title: 'History',
      blurb: 'Everything done — the full chronological activity log.',
    },
    {
      sub: 'stats',
      title: 'Stats',
      blurb: 'Funnel, reply rate, win rate, outreach volume.',
    },
  ];
  const SUB_TITLES: Record<Exclude<DashboardSub, 'home'>, string> = {
    tasks: 'Tasks',
    calendar: 'Calendar',
    history: 'History',
    stats: 'Stats',
  };
</script>

<div class="dashboard" data-testid="dashboard">
  {#if sub === 'home'}
    <header class="head">
      <h2>Dashboard</h2>
      <p class="sub">What needs your attention, and what's been done. Open any digest for the full view.</p>
    </header>

    <!-- Attention is the headline digest — full-width across the top. -->
    <section class="digest attention" data-testid="digest-attention" aria-label="Attention">
      <div class="digest-head">
        <h3>Attention{#if dashboard.count}<span class="abadge" data-testid="attention-count">{dashboard.count}</span>{/if}</h3>
      </div>
      {#if dashboard.status === 'loading'}
        <p class="placeholder">Loading…</p>
      {:else if dashboard.items.length === 0}
        <p class="placeholder">Nothing here</p>
      {:else}
        <ul class="attn-list" data-testid="attention-list">
          {#each dashboard.items as it (it.kind + (it.cluster_id || it.task_id))}
            <li class="attn-item" data-kind={it.kind}>
              {#if it.kind === 'reply'}
                <span class="attn-icon">↩</span>
                <a class="attn-link" href={leadHash(it.cluster_id)}>{it.title}</a>
                <span class="attn-when">{it.when}</span>
                <button
                  class="dismiss"
                  data-testid="dismiss-{it.cluster_id}"
                  onclick={() => dashboard.dismiss(it.cluster_id)}
                >
                  dismiss
                </button>
              {:else}
                <span class="attn-icon overdue">⏰</span>
                <a class="attn-link" href={dashboardHash('tasks')}>{it.title}</a>
                <span class="attn-when">due {it.when}</span>
              {/if}
            </li>
          {/each}
        </ul>
      {/if}
    </section>

    <div class="grid">
      {#each DIGESTS as d (d.sub)}
        <a class="digest" data-testid="digest-{d.sub}" href={dashboardHash(d.sub)}>
          <div class="digest-head">
            <h3>{d.title}{#if d.sub === 'tasks' && digestTasks.length}<span class="abadge">{digestTasks.length}</span>{/if}</h3>
          </div>
          {#if d.sub === 'tasks' && digestTasks.length}
            <ul class="mini" data-testid="tasks-digest">
              {#each digestTasks.slice(0, 4) as t (t.id)}
                <li><span class="mini-prio" class:high={t.priority === 'high'}></span>{t.title}</li>
              {/each}
            </ul>
          {:else if d.sub === 'calendar'}
            <p class="placeholder" data-testid="calendar-digest-home">
              Last contact: <strong>{activity.lastContactOn ?? '—'}</strong><br />
              Last reply: <strong>{activity.lastReplyOn ?? '—'}</strong>
            </p>
          {:else}
            <p class="placeholder">{d.blurb}</p>
          {/if}
          <span class="expand">Open {d.title} →</span>
        </a>
      {/each}
    </div>
  {:else}
    <header class="head">
      <a class="back" href={dashboardHash('home')}>‹ Dashboard</a>
      <h2>{SUB_TITLES[sub]}</h2>
    </header>
    <section class="subpage" data-testid="dashboard-subpage" data-sub={sub}>
      {#if sub === 'tasks'}
        <Tasks />
      {:else if sub === 'history'}
        <History />
      {:else if sub === 'calendar'}
        <Calendar />
      {:else if sub === 'stats'}
        <Stats />
      {:else}
        <p class="placeholder">
          The full <strong>{SUB_TITLES[sub]}</strong> workspace lands in a later slice. The
          Dashboard sub-route scaffold (deep links + back/forward) is in place.
        </p>
      {/if}
    </section>
  {/if}
</div>

<style>
  .dashboard {
    height: 100%;
    overflow-y: auto;
    padding: 18px 22px 40px;
    max-width: 1100px;
  }
  .head {
    display: flex;
    align-items: baseline;
    gap: 12px;
    flex-wrap: wrap;
  }
  h2 {
    font-size: 18px;
  }
  .sub {
    margin: 4px 0 16px;
    font-size: 12.5px;
    color: var(--text-2);
  }
  .back {
    font-size: 12.5px;
    color: var(--accent);
    text-decoration: none;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
    gap: 14px;
    margin-top: 14px;
  }
  .digest {
    display: block;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 14px 16px;
    text-decoration: none;
    color: inherit;
  }
  a.digest:hover {
    border-color: var(--accent);
  }
  .digest.attention {
    background: var(--panel-2);
  }
  .digest-head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 8px;
  }
  .digest-head h3 {
    font-size: 13px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-2);
  }
  .placeholder {
    font-size: 12.5px;
    color: var(--muted);
  }
  .expand {
    display: inline-block;
    margin-top: 10px;
    font-size: 12px;
    color: var(--accent);
  }
  .abadge {
    display: inline-block;
    margin-left: 7px;
    background: var(--accent);
    color: #fff;
    border-radius: 999px;
    padding: 0 7px;
    font-size: 11px;
    vertical-align: middle;
  }
  .attn-list {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  .attn-item {
    display: flex;
    align-items: center;
    gap: 9px;
    padding: 7px 0;
    border-bottom: 1px solid var(--border);
    font-size: 13px;
  }
  .attn-icon {
    color: var(--accent);
    font-weight: 700;
  }
  .attn-icon.overdue {
    color: var(--danger);
  }
  .attn-link {
    color: var(--text);
    text-decoration: none;
    font-weight: 600;
  }
  .attn-link:hover {
    text-decoration: underline;
  }
  .attn-when {
    color: var(--muted);
    font-size: 11.5px;
  }
  .dismiss {
    margin-left: auto;
    background: none;
    border: 1px solid var(--border-strong);
    border-radius: 999px;
    padding: 2px 10px;
    font-size: 11px;
    color: var(--text-2);
    cursor: pointer;
  }
  .mini {
    list-style: none;
    margin: 0;
    padding: 0;
    font-size: 12px;
  }
  .mini li {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 2px 0;
    color: var(--text-2);
  }
  .mini-prio {
    width: 6px;
    height: 6px;
    border-radius: 999px;
    background: var(--border-strong);
    flex-shrink: 0;
  }
  .mini-prio.high {
    background: var(--danger);
  }
  .subpage {
    margin-top: 14px;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 18px 20px;
  }
</style>
