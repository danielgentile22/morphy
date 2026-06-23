<script lang="ts">
  // Dashboard — a single scrolling page that renders all five views in full,
  // in fixed order: Attention → Tasks → Calendar → History → Stats (PRD #125,
  // supersedes the ADR-065 digest-hub + sub-pages model). The Attention feed is
  // the headline at the top; below it the full, interactive Tasks / Calendar /
  // History / Stats workspaces are stacked inline, each under one uniform
  // section heading.
  //
  // The `#/dashboard/<view>` deep link is preserved but repurposed as a scroll
  // anchor (the `sub` prop names a scroll target, not a page) — wired in #128.
  import { onMount } from 'svelte';
  import type { DashboardSub } from '../lib/nav';
  import { dashboardHash, leadHash } from '../lib/nav';
  import { dashboard } from '../lib/dashboard-store.svelte';
  import Tasks from './Tasks.svelte';
  import History from './History.svelte';
  import Calendar from './Calendar.svelte';
  import Stats from './Stats.svelte';

  let { sub }: { sub: DashboardSub } = $props();

  // The inlined views self-load their data in their own onMount; the Dashboard
  // only loads the Attention feed it renders directly. Re-opening the Dashboard
  // refreshes attention (and the views refetch via their guarded loaders, so no
  // duplicate concurrent fetches — #127).
  onMount(() => {
    void dashboard.loadAttention();
  });

  // Stable anchor id per inline view — keyed off the view name so the preserved
  // `#/dashboard/<view>` deep link can scroll to it (#128).
  const SECTION_ID: Record<Exclude<DashboardSub, 'home'>, string> = {
    tasks: 'dash-tasks',
    calendar: 'dash-calendar',
    history: 'dash-history',
    stats: 'dash-stats',
  };

  let rootEl = $state<HTMLElement>();

  function scrollToSub(s: DashboardSub): void {
    if (s === 'home') {
      rootEl?.scrollTo({ top: 0 });
    } else {
      document.getElementById(SECTION_ID[s])?.scrollIntoView({ block: 'start' });
    }
  }

  // The `#/dashboard/<view>` hash is a scroll target now, not a page selector
  // (#128): land on the named section on mount and whenever the deep-link `sub`
  // changes (e.g. the Attention overdue-task links and the Lead page's "Add one
  // in Tasks" link both point at #/dashboard/tasks). The inlined views load
  // async and reflow, so re-scroll across a short settle window to keep the
  // target in view; cancel pending scrolls on the next change / unmount.
  $effect(() => {
    const target = sub;
    const timers = [0, 80, 240].map((ms) => setTimeout(() => scrollToSub(target), ms));
    return () => timers.forEach(clearTimeout);
  });
</script>

<div class="dashboard" data-testid="dashboard" data-target={sub} bind:this={rootEl}>
  <!-- Attention — the headline, full-width at the top (data behavior unchanged). -->
  <section class="view attention" data-testid="digest-attention" aria-label="Attention">
    <h2 class="view-h">
      Attention{#if dashboard.count}<span class="chip abadge" data-tone="info" data-testid="attention-count">{dashboard.count}</span>{/if}
    </h2>
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
                class="btn btn-secondary btn-sm dismiss"
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

  <section id={SECTION_ID.tasks} class="view" data-section="tasks" aria-label="Tasks">
    <h2 class="view-h">Tasks</h2>
    <Tasks />
  </section>

  <section id={SECTION_ID.calendar} class="view" data-section="calendar" aria-label="Calendar">
    <h2 class="view-h">Calendar</h2>
    <Calendar heading={false} />
  </section>

  <section id={SECTION_ID.history} class="view" data-section="history" aria-label="History">
    <h2 class="view-h">History</h2>
    <History heading={false} />
  </section>

  <section id={SECTION_ID.stats} class="view" data-section="stats" aria-label="Stats">
    <h2 class="view-h">Stats</h2>
    <Stats heading={false} />
  </section>
</div>

<style>
  .dashboard {
    height: 100%;
    overflow-y: auto;
    padding: 18px 22px 60px;
    max-width: 1100px;
  }
  /* Each stacked view is a section with one uniform heading; a top rule and
     spacing separate it from the one above as you scroll. */
  .view {
    padding-top: 22px;
    margin-top: 22px;
    border-top: 1px solid var(--border);
  }
  /* The headline Attention section sits flush at the very top — no rule above. */
  .view.attention {
    padding-top: 0;
    margin-top: 0;
    border-top: none;
  }
  .view-h {
    font-size: 18px;
    margin-bottom: 14px;
  }
  .placeholder {
    font-size: 12.5px;
    color: var(--muted);
  }
  .abadge {
    margin-left: 7px;
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
  }
</style>
