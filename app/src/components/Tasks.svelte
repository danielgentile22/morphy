<script lang="ts">
  // Tasks workspace (UI overhaul P2 / #107 + #110) — create / list / complete,
  // with links (owner/tower), assignee, due, priority, labels, and filter-by-
  // any-field + free-text search. Rendered as the Dashboard `tasks` sub-page.
  import { onMount } from 'svelte';
  import { tasks } from '../lib/tasks-store.svelte';
  import { auth } from '../lib/auth-store.svelte';
  import { leadHash, towerHash, settingsHash } from '../lib/nav';
  import Icon from './Icon.svelte';
  import type { Task, TaskStatus, TaskPriority } from '../lib/tasks-api';

  // The auto-follow-up automation moved to Settings → Automations (PRD #121);
  // Tasks keeps only a pointer to it (below).

  // ── create form ─────────────────────────────────────────────────────────
  let draft = $state({
    title: '',
    description: '',
    priority: 'none' as TaskPriority,
    due_date: '',
    assignee_user_id: '' as string,
    lead_cluster_id: '',
    tower_asr: '',
    labels: '',
  });
  let showDetails = $state(false);

  onMount(() => {
    void tasks.load();
    void tasks.loadUsers();
  });

  async function add(): Promise<void> {
    const ok = await tasks.create({
      title: draft.title,
      description: draft.description,
      priority: draft.priority,
      due_date: draft.due_date || null,
      assignee_user_id: draft.assignee_user_id ? Number(draft.assignee_user_id) : null,
      lead_cluster_id: draft.lead_cluster_id || null,
      tower_asr: draft.tower_asr || null,
      labels: draft.labels
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean),
    });
    if (ok) {
      draft = {
        title: '',
        description: '',
        priority: 'none',
        due_date: '',
        assignee_user_id: '',
        lead_cluster_id: '',
        tower_asr: '',
        labels: '',
      };
    }
  }

  const STATUS_LABEL: Record<TaskStatus, string> = {
    open: 'Open',
    in_progress: 'In progress',
    done: 'Done',
  };
  // Halo chip tone for the cycle-status pill + the priority badge (decorative;
  // the text label always rides along, so colorblind-safe).
  const STATUS_TONE: Record<TaskStatus, 'neutral' | 'info' | 'success'> = {
    open: 'neutral',
    in_progress: 'info',
    done: 'success',
  };
  const PRIO_TONE: Record<TaskPriority, '' | 'neutral' | 'warning' | 'danger'> = {
    none: '',
    low: 'neutral',
    med: 'warning',
    high: 'danger',
  };
  const NEXT: Record<TaskStatus, TaskStatus> = {
    open: 'in_progress',
    in_progress: 'done',
    done: 'open',
  };
  function toggleDone(t: Task): void {
    void tasks.setStatus(t.id, t.status === 'done' ? 'open' : 'done');
  }
  function cycle(t: Task): void {
    void tasks.setStatus(t.id, NEXT[t.status]);
  }
</script>

<div class="tasks" data-testid="tasks">
  <!-- Auto follow-up relocated to Settings → Automations (PRD #121). -->
  <p class="auto-pointer" data-testid="automation-pointer">
    Auto follow-up is configured in <a href={settingsHash()}>Settings → Automations</a>.
  </p>

  {#if !auth.readOnly}
  <form
    class="newtask"
    data-testid="task-form"
    onsubmit={(e) => {
      e.preventDefault();
      void add();
    }}
  >
    <div class="newtask-row">
      <input class="input t-title" data-testid="task-title" bind:value={draft.title} placeholder="New task…" aria-label="Task title" />
      <input class="input t-desc" data-testid="task-desc" bind:value={draft.description} placeholder="Description (optional)" aria-label="Task description" />
      <button type="button" class="btn btn-secondary" onclick={() => (showDetails = !showDetails)}>
        {showDetails ? 'Less' : 'More'}
      </button>
      <button class="btn btn-primary" type="submit" data-testid="task-add" disabled={tasks.saving || !draft.title.trim()}>
        Add
      </button>
    </div>
    {#if showDetails}
      <div class="newtask-details" data-testid="task-details">
        <label>Priority
          <select bind:value={draft.priority} data-testid="task-priority">
            <option value="none">none</option><option value="low">low</option>
            <option value="med">med</option><option value="high">high</option>
          </select>
        </label>
        <label>Due
          <input type="date" bind:value={draft.due_date} data-testid="task-due" />
        </label>
        <label>Assignee
          <select bind:value={draft.assignee_user_id} data-testid="task-assignee">
            <option value="">Unassigned</option>
            {#each tasks.users as u (u.id)}<option value={String(u.id)}>{u.name}</option>{/each}
          </select>
        </label>
        <label>Owner (cid)
          <input bind:value={draft.lead_cluster_id} placeholder="display_cluster_id" data-testid="task-lead" />
        </label>
        <label>Tower (ASR)
          <input bind:value={draft.tower_asr} placeholder="ASR" data-testid="task-tower" />
        </label>
        <label>Labels
          <input bind:value={draft.labels} placeholder="comma,separated" data-testid="task-labels" />
        </label>
      </div>
    {/if}
  </form>
  {/if}

  <!-- filter bar -->
  <div class="filterbar" data-testid="task-filter">
    <input
      class="search"
      data-testid="task-search"
      placeholder="Search title/description…"
      value={tasks.filter.q}
      oninput={(e) => tasks.setFilter({ q: e.currentTarget.value })}
      aria-label="Search tasks"
    />
    <select aria-label="Status" data-testid="filter-status" value={tasks.filter.status} onchange={(e) => tasks.setFilter({ status: e.currentTarget.value as any })}>
      <option value="">any status</option><option value="open">open</option>
      <option value="in_progress">in progress</option><option value="done">done</option>
    </select>
    <select aria-label="Priority" data-testid="filter-priority" value={tasks.filter.priority} onchange={(e) => tasks.setFilter({ priority: e.currentTarget.value as any })}>
      <option value="">any priority</option><option value="high">high</option>
      <option value="med">med</option><option value="low">low</option><option value="none">none</option>
    </select>
    <select aria-label="Assignee" data-testid="filter-assignee" value={tasks.filter.unassigned ? 'un' : tasks.filter.assignee == null ? '' : String(tasks.filter.assignee)} onchange={(e) => {
      const v = e.currentTarget.value;
      tasks.setFilter({ unassigned: v === 'un', assignee: v && v !== 'un' ? Number(v) : null });
    }}>
      <option value="">any assignee</option><option value="un">unassigned</option>
      {#each tasks.users as u (u.id)}<option value={String(u.id)}>{u.name}</option>{/each}
    </select>
    <select aria-label="Due" data-testid="filter-due" value={tasks.filter.dueWindow} onchange={(e) => tasks.setFilter({ dueWindow: e.currentTarget.value as any })}>
      <option value="">any due</option><option value="overdue">overdue</option>
      <option value="today">due ≤ today</option><option value="week">due ≤ 1 week</option>
    </select>
    <input class="lbl" placeholder="label" value={tasks.filter.label} oninput={(e) => tasks.setFilter({ label: e.currentTarget.value })} aria-label="Label" data-testid="filter-label" />
    <button class="clear" onclick={() => tasks.resetFilter()}>Clear</button>
  </div>

  {#if tasks.error}<p class="err" data-testid="task-error">{tasks.error}</p>{/if}

  {#if tasks.status === 'loading'}
    <p class="muted">Loading tasks…</p>
  {:else if tasks.visible.length === 0}
    <p class="muted" data-testid="task-empty">
      {tasks.tasks.length === 0 ? (auth.readOnly ? 'No tasks yet.' : 'No tasks yet. Add one above.') : 'No tasks match the filter.'}
    </p>
  {:else}
    <ul class="list" data-testid="task-list">
      {#each tasks.visible as t (t.id)}
        <li class="row" class:done={t.status === 'done'} data-testid="task-row" data-status={t.status}>
          <input type="checkbox" class="check" data-testid="task-check" checked={t.status === 'done'} onchange={() => toggleDone(t)} aria-label="Toggle done" disabled={auth.readOnly} />
          <div class="body">
            <div class="line1">
              <span class="ttitle">{t.title}</span>
              {#if t.priority !== 'none'}<span class="chip" data-tone={PRIO_TONE[t.priority] || undefined}>{t.priority}</span>{/if}
              {#if t.due_date}<span class="chip" data-tone="warning">due {t.due_date}</span>{/if}
              {#if t.source === 'auto'}<span class="chip" data-tone="info">auto</span>{/if}
            </div>
            {#if t.description}<span class="tdesc">{t.description}</span>{/if}
            <div class="meta">
              <span class="assignee">{tasks.userName(t.assignee_user_id)}</span>
              {#if t.lead_cluster_id}<a class="link" href={leadHash(t.lead_cluster_id)}>owner</a>{/if}
              {#if t.tower_asr && t.lead_cluster_id}<a class="link" href={towerHash(t.lead_cluster_id, t.tower_asr)}>ASR {t.tower_asr}</a>
              {:else if t.tower_asr}<span class="link muted">ASR {t.tower_asr}</span>{/if}
              {#each t.labels as l (l)}<span class="chip" data-tone="neutral">{l}</span>{/each}
            </div>
          </div>
          <button class="chip status-pill" data-testid="task-status" data-status={t.status} data-tone={STATUS_TONE[t.status]} onclick={() => cycle(t)} disabled={auth.readOnly} title={auth.readOnly ? 'Read-only demo' : 'Cycle status'}>
            {STATUS_LABEL[t.status]}
          </button>
          {#if !auth.readOnly}
            <button class="del" data-testid="task-delete" onclick={() => tasks.remove(t.id)} aria-label="Delete task"><Icon name="x" size={15} /></button>
          {/if}
        </li>
      {/each}
    </ul>
  {/if}
</div>

<style>
  /* No width cap — fills the dashboard column (.dash-inner); Tasks is only ever
     rendered there. */
  .auto-pointer {
    margin: 0 0 12px;
    padding: 8px 12px;
    background: var(--panel-2);
    border-radius: var(--radius);
    font-size: 12.5px;
    color: var(--muted);
  }
  .newtask {
    margin-bottom: 12px;
  }
  .newtask-row {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }
  .t-title,
  .t-desc {
    flex: 1;
    min-width: 150px;
  }
  .newtask-details {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    margin-top: 8px;
    padding: 10px;
    background: var(--panel-2);
    border-radius: var(--radius);
  }
  .newtask-details label {
    display: flex;
    flex-direction: column;
    font-size: 10.5px;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    color: var(--muted);
    gap: 3px;
  }
  .newtask-details input,
  .newtask-details select {
    font: inherit;
    font-size: 12.5px;
    padding: 5px 7px;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius);
    background: var(--panel);
    color: var(--text);
  }
  .filterbar {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    align-items: center;
    margin-bottom: 12px;
    padding-bottom: 10px;
    border-bottom: 1px solid var(--border);
  }
  .filterbar .search {
    flex: 1;
    min-width: 160px;
  }
  .filterbar input,
  .filterbar select {
    font: inherit;
    font-size: 12px;
    padding: 5px 8px;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius);
    background: var(--panel);
    color: var(--text);
  }
  .filterbar .lbl {
    width: 90px;
  }
  .clear {
    background: none;
    border: none;
    color: var(--accent);
    font-size: 12px;
    cursor: pointer;
  }
  .err {
    color: var(--danger);
    font-size: 12.5px;
  }
  .muted {
    color: var(--muted);
    font-size: 13px;
  }
  .list {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  .row {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    padding: 9px 4px;
    border-bottom: 1px solid var(--border);
  }
  .check {
    margin-top: 3px;
    flex-shrink: 0;
  }
  .body {
    flex: 1;
    min-width: 0;
  }
  .line1 {
    display: flex;
    align-items: center;
    gap: 7px;
    flex-wrap: wrap;
  }
  .ttitle {
    font-size: 13.5px;
    font-weight: 600;
  }
  .row.done .ttitle {
    text-decoration: line-through;
    color: var(--muted);
  }
  .tdesc {
    display: block;
    font-size: 12px;
    color: var(--muted);
  }
  .meta {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
    margin-top: 3px;
    font-size: 11.5px;
    color: var(--muted);
  }
  .meta .link {
    color: var(--accent);
    text-decoration: none;
  }
  .meta .link.muted {
    color: var(--muted);
  }
  .status-pill {
    flex-shrink: 0;
    cursor: pointer;
  }
  .status-pill:disabled {
    cursor: default;
  }
  .del {
    flex-shrink: 0;
    display: inline-flex;
    align-items: center;
    margin-top: 3px;
    background: none;
    border: none;
    color: var(--muted);
    cursor: pointer;
  }
  .del:hover {
    color: var(--text);
  }
</style>
