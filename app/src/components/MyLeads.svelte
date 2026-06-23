<script lang="ts">
  import { leads } from '../lib/leads-store.svelte';
  import { scoring } from '../lib/scoring-store.svelte';
  import {
    KANBAN_LANES,
    STATUS_LABELS,
    TERMINAL_STATUSES,
    canTransition,
    type LeadStatus,
  } from '../lib/lead-status';
  import { kindLabel, statusVar, statusGlyph } from '../lib/lead-format';
  import { leadHash, SECTION_HASH } from '../lib/nav';
  import type { OwnerSummary } from '../lib/leads-api';

  // The Leads surface (parent) owns the data load; this is just the board lens.

  // Bucket the worklist into lanes. Reactive on leads.myLeads (and each
  // owner's .status), so an optimistic drag re-renders both lanes at once.
  // Within each lane, cards rank by the active scoring config so a preset
  // switch re-orders the board consistently with Explore + the list (#115).
  const byLane = $derived.by(() => {
    const m: Record<string, OwnerSummary[]> = {};
    for (const lane of KANBAN_LANES) m[lane] = [];
    for (const o of leads.myLeads) (m[o.status] ??= []).push(o);
    for (const lane of Object.keys(m)) {
      m[lane].sort(
        (a, b) =>
          (scoring.scoreOf(b.display_cluster_id) ?? -Infinity) -
          (scoring.scoreOf(a.display_cluster_id) ?? -Infinity),
      );
    }
    return m;
  });

  // Native HTML5 drag-and-drop (no library). The card being dragged + the
  // lane currently hovered drive the legal/illegal drop affordance.
  let draggingId = $state<string | null>(null);
  let draggingFrom = $state<LeadStatus | null>(null);
  let overLane = $state<string | null>(null);

  function onDragStart(e: DragEvent, o: OwnerSummary): void {
    draggingId = o.display_cluster_id;
    draggingFrom = o.status;
    if (e.dataTransfer) {
      e.dataTransfer.setData('text/plain', o.display_cluster_id);
      e.dataTransfer.effectAllowed = 'move';
    }
  }
  function onDragEnd(): void {
    draggingId = null;
    draggingFrom = null;
    overLane = null;
  }
  function legalInto(lane: LeadStatus): boolean {
    return draggingFrom !== null && canTransition(draggingFrom, lane);
  }
  function onDragOver(e: DragEvent, lane: LeadStatus): void {
    overLane = lane;
    if (legalInto(lane)) {
      e.preventDefault(); // allow the drop
      if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
    } else if (e.dataTransfer) {
      e.dataTransfer.dropEffect = 'none';
    }
  }
  function onDragLeave(lane: LeadStatus): void {
    if (overLane === lane) overLane = null;
  }
  async function onDrop(e: DragEvent, lane: LeadStatus): Promise<void> {
    e.preventDefault();
    const id = e.dataTransfer?.getData('text/plain') || draggingId;
    overLane = null;
    if (id) await leads.moveLead(id, lane); // server is authoritative; reverts on reject
  }

  function open(id: string): void {
    location.hash = leadHash(id);
  }
</script>

<div class="myleads" data-testid="my-leads">
  <header class="head">
    <p class="sub">
      Owners you’ve advanced off “New”. Drag a card between lanes to change its status — the change
      is auto-logged and persists. New owners live in
      <button class="link" onclick={() => (location.hash = SECTION_HASH.explore)}>Explore</button>.
    </p>
  </header>

  {#if leads.myLeadsError}
    <p class="state-msg err" data-testid="my-leads-error">{leads.myLeadsError}</p>
  {/if}

  {#if leads.myLeadsStatus === 'loading'}
    <p class="state-msg">Loading worklist…</p>
  {:else if leads.myLeadsStatus === 'error'}
    <p class="state-msg err">{leads.myLeadsError}</p>
  {:else}
    <div class="kanban" data-testid="kanban">
      {#each KANBAN_LANES as lane (lane)}
        {@const cards = byLane[lane] ?? []}
        <section
          class="lane"
          class:closed={TERMINAL_STATUSES.has(lane)}
          class:dragover={overLane === lane}
          class:legal={overLane === lane && draggingId !== null && legalInto(lane)}
          class:illegal={overLane === lane && draggingId !== null && !legalInto(lane)}
          data-testid="lane"
          data-lane={lane}
          role="group"
          aria-label="{STATUS_LABELS[lane]} lane"
          ondragover={(e) => onDragOver(e, lane)}
          ondragleave={() => onDragLeave(lane)}
          ondrop={(e) => onDrop(e, lane)}
        >
          <div class="lane-head" style="border-color:{statusVar(lane)}">
            <span class="dot" style="background:{statusVar(lane)}"></span>
            <span class="cb-cue" aria-hidden="true">{statusGlyph(lane)}</span>
            {STATUS_LABELS[lane]}
            <span class="count" data-testid="lane-count">{cards.length}</span>
          </div>
          <div class="lane-body">
            {#each cards as o (o.display_cluster_id)}
              <div
                class="card"
                data-testid="lead-card"
                data-key={o.display_cluster_id}
                data-status={o.status}
                draggable="true"
                role="button"
                tabindex="0"
                aria-label="Open lead {o.owner_name}"
                ondragstart={(e) => onDragStart(e, o)}
                ondragend={onDragEnd}
                onclick={() => open(o.display_cluster_id)}
                onkeydown={(e) => e.key === 'Enter' && open(o.display_cluster_id)}
              >
                <div class="cname">{o.owner_name}</div>
                <div class="cmeta">
                  <span>{kindLabel(o.owner_kind)}</span>
                  <span>{o.states.join('/')}</span>
                  <span>{o.tower_count} twr</span>
                  {#if o.cross_state}<span class="x">multi-state</span>{/if}
                  {#if o.distress_tier === 'distressed'}
                    <span class="distress-high">high distress</span>
                  {/if}
                </div>
                {#if o.trigger_asr}
                  <div class="trigger" data-testid="card-trigger">⚑ flagged from ASR {o.trigger_asr}</div>
                {/if}
              </div>
            {/each}
            {#if cards.length === 0}
              <p class="empty">—</p>
            {/if}
          </div>
        </section>
      {/each}
    </div>
  {/if}
</div>

<style>
  .myleads {
    display: flex;
    flex-direction: column;
    height: 100%;
    padding: 4px 22px 0;
  }
  .head {
    flex-shrink: 0;
  }
  .sub {
    margin: 0 0 14px;
    font-size: 12.5px;
    color: var(--text-2);
    max-width: 760px;
  }
  .link {
    background: none;
    border: none;
    padding: 0;
    color: var(--accent);
    font: inherit;
  }
  .state-msg {
    font-size: 13px;
    color: var(--muted);
  }
  .state-msg.err {
    color: var(--danger);
  }

  /* Board: a row of lanes that fill the surface width. Lanes size to their
     content (top-aligned), so the board is only as tall as the fullest lane;
     the whole board scrolls as one unit when that exceeds the surface — no
     per-lane scrollbars. */
  .kanban {
    display: flex;
    align-items: flex-start;
    gap: 14px;
    flex: 1;
    min-height: 0;
    overflow: auto;
    padding-bottom: 18px;
  }
  .lane {
    flex: 1 1 0;
    min-width: 240px;
    max-width: 360px;
    display: flex;
    flex-direction: column;
    background: var(--panel-2);
    border: 1px solid var(--border);
    border-radius: var(--radius);
  }
  .lane.closed {
    background: var(--color-danger-soft);
  }
  /* Drop affordance while dragging. */
  .lane.dragover.legal {
    outline: 2px dashed var(--accent);
    outline-offset: -4px;
  }
  .lane.dragover.illegal {
    outline: 2px dashed var(--danger);
    outline-offset: -4px;
    cursor: not-allowed;
  }
  .lane-head {
    display: flex;
    align-items: center;
    gap: 7px;
    padding: 10px 12px;
    font-weight: 650;
    font-size: 13px;
    border-bottom: 2px solid;
  }
  .lane-head .dot {
    width: 8px;
    height: 8px;
    border-radius: 999px;
  }
  .lane-head .count {
    margin-left: auto;
    font-size: 11px;
    font-weight: 600;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 999px;
    padding: 0 7px;
    color: var(--text-2);
  }
  .lane-body {
    min-height: 48px;
    padding: 8px;
  }
  .card {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 9px 10px;
    margin-bottom: 8px;
    box-shadow: var(--shadow);
    cursor: grab;
  }
  .card:active {
    cursor: grabbing;
  }
  .card .cname {
    font-weight: 600;
    font-size: 13px;
  }
  .card .cmeta {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 4px;
    font-size: 11.5px;
    color: var(--muted);
  }
  .card .cmeta .x {
    color: var(--color-info);
  }
  .card .trigger {
    margin-top: 4px;
    font-size: 11px;
    color: var(--color-warning);
  }
  .distress-high {
    color: var(--danger);
    font-weight: 600;
  }
  .empty {
    margin: 4px 0 0;
    text-align: center;
    color: var(--muted);
    font-size: 13px;
  }
</style>
