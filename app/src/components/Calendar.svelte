<script lang="ts">
  // Calendar sub-page (UI overhaul P3 / #112) — the activity stream + task
  // due-dates on a month grid (the time-grid lens; History is the list lens).
  // Reads the same /api/activity model + the tasks store for due-dates.
  import { onMount } from 'svelte';
  import { activity } from '../lib/activity-store.svelte';
  import { tasks } from '../lib/tasks-store.svelte';
  import { leadHash } from '../lib/nav';

  // When embedded in the single scrolling Dashboard (PRD #125) the Dashboard
  // supplies one uniform section heading, so it passes heading={false} to
  // suppress this component's own <h2> and avoid a double title. Default true
  // keeps the standalone render self-titled.
  let { heading = true }: { heading?: boolean } = $props();

  const now = new Date();
  let year = $state(now.getUTCFullYear());
  let month = $state(now.getUTCMonth()); // 0-based
  let selected = $state<string | null>(null);

  onMount(() => {
    void activity.load();
    void tasks.load();
  });

  function iso(y: number, m: number, d: number): string {
    return `${y}-${String(m + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
  }

  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

  // The grid: leading blanks + each day of the month.
  const cells = $derived.by(() => {
    const firstDow = new Date(Date.UTC(year, month, 1)).getUTCDay();
    const days = new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
    const out: (string | null)[] = [];
    for (let i = 0; i < firstDow; i++) out.push(null);
    for (let d = 1; d <= days; d++) out.push(iso(year, month, d));
    return out;
  });

  // date → { activity count, due tasks }.
  const byDate = $derived.by(() => {
    const m = new Map<string, { acts: number; due: { id: number; title: string }[] }>();
    const get = (d: string) => {
      let e = m.get(d);
      if (!e) m.set(d, (e = { acts: 0, due: [] }));
      return e;
    };
    for (const e of activity.events) get(e.date).acts++;
    for (const t of tasks.tasks) if (t.due_date && t.status !== 'done') get(t.due_date).due.push({ id: t.id, title: t.title });
    return m;
  });

  const selectedActs = $derived(selected ? activity.events.filter((e) => e.date === selected) : []);
  const selectedDue = $derived(selected ? (byDate.get(selected)?.due ?? []) : []);

  function prev(): void {
    if (month === 0) {
      month = 11;
      year--;
    } else month--;
  }
  function next(): void {
    if (month === 11) {
      month = 0;
      year++;
    } else month++;
  }
</script>

<div class="calendar" data-testid="calendar">
  <header class="head">
    {#if heading}<h2>Calendar</h2>{/if}
    <div class="digest" data-testid="calendar-digest">
      Last contact: <b>{activity.lastContactOn ?? '—'}</b> · Last reply:
      <b>{activity.lastReplyOn ?? '—'}</b>
    </div>
  </header>

  <div class="monthnav">
    <button onclick={prev} aria-label="Previous month">‹</button>
    <span class="mlabel">{MONTHS[month]} {year}</span>
    <button onclick={next} aria-label="Next month">›</button>
  </div>

  <div class="grid" data-testid="calendar-grid">
    {#each ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'] as dow (dow)}
      <div class="dow">{dow}</div>
    {/each}
    {#each cells as c, i (i)}
      {#if c === null}
        <div class="cell empty"></div>
      {:else}
        {@const info = byDate.get(c)}
        <button
          class="cell"
          class:has={!!info}
          class:on={selected === c}
          data-testid="day-{c}"
          onclick={() => (selected = c)}
        >
          <span class="dnum">{Number(c.slice(-2))}</span>
          {#if info?.acts}<span class="badge acts">{info.acts}</span>{/if}
          {#if info?.due.length}<span class="badge due">⏰{info.due.length}</span>{/if}
        </button>
      {/if}
    {/each}
  </div>

  {#if selected}
    <section class="daydetail" data-testid="day-detail">
      <h3>{selected}</h3>
      {#if selectedActs.length === 0 && selectedDue.length === 0}
        <p class="muted">Nothing on this day.</p>
      {:else}
        <ul>
          {#each selectedDue as t (t.id)}
            <li>⏰ <b>Task due:</b> {t.title}</li>
          {/each}
          {#each selectedActs as e (e.id)}
            <li>
              {e.kind === 'reply' ? '↩' : e.kind === 'flag' ? '⚑' : '→'}
              <a href={leadHash(e.cluster_id)}>{e.owner_name || e.cluster_id}</a>
              — {e.channel} {e.summary}
            </li>
          {/each}
        </ul>
      {/if}
    </section>
  {/if}
</div>

<style>
  /* No width cap — fills the dashboard column (.dash-inner). */
  .head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 12px;
    flex-wrap: wrap;
    margin-bottom: 10px;
  }
  h2 {
    font-size: 18px;
  }
  .digest {
    font-size: 12.5px;
    color: var(--muted);
  }
  .monthnav {
    display: flex;
    align-items: center;
    gap: 14px;
    margin-bottom: 10px;
  }
  .monthnav button {
    border: 1px solid var(--border-strong);
    background: var(--panel);
    border-radius: var(--radius);
    width: 28px;
    height: 28px;
    font-size: 15px;
    cursor: pointer;
  }
  .mlabel {
    font-weight: 600;
    font-size: 14px;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(7, 1fr);
    gap: 4px;
  }
  .dow {
    text-align: center;
    font-size: 11px;
    color: var(--muted);
    padding: 2px 0;
  }
  .cell {
    position: relative;
    min-height: 56px;
    border: 1px solid var(--border);
    border-radius: 5px;
    background: var(--panel);
    padding: 4px 5px;
    text-align: left;
    cursor: pointer;
  }
  .cell.empty {
    border: none;
    background: none;
    cursor: default;
  }
  .cell.has {
    border-color: var(--border-strong);
  }
  .cell.on {
    outline: 2px solid var(--accent);
    outline-offset: -2px;
  }
  .dnum {
    font-size: 11.5px;
    color: var(--text-2);
  }
  .badge {
    display: inline-block;
    margin-top: 4px;
    margin-right: 3px;
    font-size: 10px;
    padding: 0 5px;
    border-radius: 999px;
  }
  .badge.acts {
    background: var(--accent);
    color: #fff;
  }
  .badge.due {
    background: var(--color-warning-soft);
    color: var(--color-warning);
  }
  .daydetail {
    margin-top: 14px;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 12px 16px;
  }
  .daydetail h3 {
    font-size: 13px;
    margin-bottom: 8px;
  }
  .daydetail ul {
    list-style: none;
    margin: 0;
    padding: 0;
    font-size: 12.5px;
  }
  .daydetail li {
    padding: 4px 0;
    border-bottom: 1px solid var(--border);
  }
  .daydetail a {
    color: var(--accent);
    text-decoration: none;
  }
  .muted {
    color: var(--muted);
    font-size: 13px;
  }
</style>
