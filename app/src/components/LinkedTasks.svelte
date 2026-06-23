<script lang="ts">
  // Owner/tower-linked tasks (UI overhaul P2 / #110) — surfaced on the Lead
  // page + tower detail so task context lives where you work. Fetches its tasks
  // server-side via the shared task-filter query (lead=… or tower=…).
  import { fetchTasks, type Task } from '../lib/tasks-api';
  import { dashboardHash } from '../lib/nav';

  let { query, heading = 'Tasks' }: { query: string; heading?: string } = $props();

  let items = $state<Task[]>([]);
  let loaded = $state(false);

  $effect(() => {
    loaded = false;
    void fetchTasks(query)
      .then((r) => {
        items = r.tasks;
      })
      .catch(() => {
        items = [];
      })
      .finally(() => {
        loaded = true;
      });
  });
</script>

<section class="card" data-testid="linked-tasks">
  <h3>{heading}{#if items.length}<span class="n"> · {items.length}</span>{/if}</h3>
  {#if !loaded}
    <p class="muted small">Loading…</p>
  {:else if items.length === 0}
    <p class="muted small">
      No linked tasks. Add one in <a href={dashboardHash('tasks')}>Tasks</a>.
    </p>
  {:else}
    <ul class="ltasks">
      {#each items as t (t.id)}
        <li class:done={t.status === 'done'}>
          <span class="dot" data-status={t.status}></span>
          <span class="lt-title">{t.title}</span>
          {#if t.priority !== 'none'}<span class="lt-prio">{t.priority}</span>{/if}
          {#if t.due_date}<span class="lt-due">due {t.due_date}</span>{/if}
        </li>
      {/each}
    </ul>
  {/if}
</section>

<style>
  .card {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 14px 16px;
  }
  .card h3 {
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
    margin-bottom: 8px;
  }
  .n {
    color: var(--text-2);
  }
  .muted {
    color: var(--muted);
  }
  .small {
    font-size: 11.5px;
  }
  .muted a {
    color: var(--accent);
  }
  .ltasks {
    list-style: none;
    margin: 0;
    padding: 0;
    font-size: 12.5px;
  }
  .ltasks li {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 5px 0;
    border-bottom: 1px solid var(--border);
  }
  .ltasks li.done .lt-title {
    text-decoration: line-through;
    color: var(--muted);
  }
  .dot {
    width: 8px;
    height: 8px;
    border-radius: 999px;
    background: var(--border-strong);
    flex-shrink: 0;
  }
  .dot[data-status='in_progress'] {
    background: var(--accent);
  }
  .dot[data-status='done'] {
    background: var(--color-success);
  }
  .lt-title {
    flex: 1;
  }
  .lt-prio,
  .lt-due {
    font-size: 10.5px;
    color: var(--muted);
  }
</style>
