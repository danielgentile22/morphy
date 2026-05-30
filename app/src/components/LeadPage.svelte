<script lang="ts">
  import { leads } from '../lib/leads-store.svelte';
  import { STATUSES, STATUS_LABELS, canTransition, type LeadStatus } from '../lib/lead-status';
  import { kindLabel, money, distressText, statusVar } from '../lib/lead-format';

  let { displayClusterId }: { displayClusterId: string } = $props();

  // (Re)load whenever the routed key changes.
  $effect(() => {
    void leads.loadLead(displayClusterId);
  });

  // Local notes draft, seeded from the loaded lead.
  let noteDraft = $state('');
  let loadedFor = '';
  $effect(() => {
    const l = leads.lead;
    if (l && l.owner.display_cluster_id !== loadedFor) {
      noteDraft = l.notes;
      loadedFor = l.owner.display_cluster_id;
    }
  });

  async function setStatus(s: LeadStatus): Promise<void> {
    const l = leads.lead;
    if (!l || s === l.status) return;
    await leads.saveLead(displayClusterId, { status: s });
  }

  async function saveNote(): Promise<void> {
    await leads.saveLead(displayClusterId, { notes: noteDraft });
  }

  function back(): void {
    location.hash = '#/candidates';
  }
</script>

<div class="lead" data-testid="lead-page">
  <button class="back" onclick={back}>‹ back to Candidates</button>

  {#if leads.leadStatus === 'loading'}
    <p class="state-msg">Loading lead…</p>
  {:else if leads.leadStatus === 'error'}
    <p class="state-msg err" data-testid="lead-error">{leads.leadError}</p>
  {:else if leads.lead}
    {@const l = leads.lead}
    {@const o = l.owner}
    <header class="head">
      <span class="dot" style="background:{statusVar(l.status)}"></span>
      <h1>{o.owner_name}</h1>
      <span class="tag">{kindLabel(o.owner_kind)}</span>
      {#each o.states as s (s)}
        <span class="tag state">{s}</span>
      {/each}
      {#if o.cross_state}
        <span class="tag x">cross-state lead</span>
      {/if}
    </header>

    <div class="cols">
      <section class="card">
        <h3>Why this lead</h3>
        <div class="pills">
          <div class="pill"><b>{o.score.toFixed(2)}</b><span>score</span></div>
          <div class="pill"><b>{o.parcel_count}</b><span>parcels</span></div>
          <div class="pill"><b>{o.tower_count}</b><span>towers</span></div>
          <div class="pill"><b>{money(o.total_assessed_value)}</b><span>assessed</span></div>
        </div>
        <div class="distress">
          <span class="label">Distress</span>
          <span class={o.distress_tier === 'distressed' ? 'distress-high' : ''}>{distressText(o)}</span>
        </div>
        <p class="muted small">
          Holdings detail, mailing address, and the contact-attempts editor arrive in a later slice;
          this tracer proves the cross-state key + write path.
        </p>
      </section>

      <section class="card">
        <h3>Status</h3>
        <div class="statusbtns" data-testid="status-selector">
          {#each STATUSES as s (s)}
            <button
              class="sbtn"
              class:on={l.status === s}
              style={l.status === s ? `background:${statusVar(s)};border-color:${statusVar(s)};color:#fff` : ''}
              disabled={!canTransition(l.status, s)}
              data-status={s}
              onclick={() => setStatus(s)}
            >
              {STATUS_LABELS[s]}
            </button>
          {/each}
        </div>
        <p class="ladder muted small">
          New → Researching → Contacted → (Interested → In Business) | Uninterested
        </p>
        {#if leads.saveError}
          <p class="state-msg err" data-testid="save-error">{leads.saveError}</p>
        {/if}

        <h3 class="mt">Notes</h3>
        <textarea
          class="notes"
          data-testid="notes"
          bind:value={noteDraft}
          placeholder="Free-text notes…"
        ></textarea>
        <button class="save" data-testid="save-note" onclick={saveNote} disabled={leads.saving}>
          {leads.saving ? 'Saving…' : 'Save note'}
        </button>

        {#if l.attempts.length}
          <h3 class="mt">Activity</h3>
          <ul class="activity">
            {#each l.attempts as a (a.id)}
              <li>
                <span class="muted">{a.occurred_on}</span>
                <span>{a.channel}</span>
                <span>{a.outcome}</span>
              </li>
            {/each}
          </ul>
        {/if}
      </section>
    </div>
  {/if}
</div>

<style>
  .lead {
    padding: 16px 22px 40px;
    max-width: 1000px;
  }
  .back {
    display: inline-block;
    font-size: 12.5px;
    margin-bottom: 12px;
    background: none;
    border: none;
    padding: 0;
    color: var(--accent);
  }
  .state-msg {
    font-size: 13px;
    color: var(--muted);
  }
  .state-msg.err {
    color: var(--danger);
  }
  .head {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
    margin-bottom: 16px;
  }
  .head h1 {
    font-size: 20px;
  }
  .dot {
    width: 11px;
    height: 11px;
    border-radius: 999px;
  }
  .cols {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
  }
  @media (max-width: 820px) {
    .cols {
      grid-template-columns: 1fr;
    }
  }
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
    margin-bottom: 10px;
  }
  .card h3.mt {
    margin-top: 18px;
  }
  .pills {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
  .pill {
    display: flex;
    flex-direction: column;
    align-items: center;
    min-width: 64px;
    padding: 7px 10px;
    background: var(--panel-2);
    border-radius: var(--radius);
  }
  .pill b {
    font-size: 15px;
  }
  .pill span {
    font-size: 10.5px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .distress {
    margin-top: 12px;
    font-size: 13px;
  }
  .distress .label {
    display: block;
    font-size: 11px;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 3px;
  }
  .distress-high {
    color: var(--danger);
    font-weight: 600;
  }
  .tag {
    display: inline-block;
    padding: 2px 7px;
    font-size: 11px;
    border-radius: 3px;
    background: var(--panel-2);
    border: 1px solid var(--border);
    color: var(--text-2);
  }
  .tag.x {
    background: #efe7fb;
    border-color: #d9c8f5;
    color: #5a3aa8;
  }
  .statusbtns {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  .sbtn {
    padding: 6px 11px;
    font-size: 12.5px;
    border: 1px solid var(--border-strong);
    background: var(--panel);
    color: var(--text-2);
    border-radius: var(--radius);
  }
  .sbtn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
  .ladder {
    margin-top: 8px;
  }
  .muted {
    color: var(--muted);
  }
  .small {
    font-size: 11.5px;
  }
  .notes {
    width: 100%;
    min-height: 90px;
    resize: vertical;
    font-family: inherit;
    font-size: 13px;
    padding: 8px 10px;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius);
  }
  .save {
    margin-top: 8px;
    padding: 7px 14px;
    font-size: 12.5px;
    border: 1px solid var(--accent);
    background: var(--accent);
    color: #fff;
    border-radius: var(--radius);
  }
  .save:disabled {
    opacity: 0.6;
  }
  .activity {
    list-style: none;
    margin: 0;
    padding: 0;
    font-size: 12.5px;
  }
  .activity li {
    display: flex;
    gap: 10px;
    padding: 5px 0;
    border-bottom: 1px solid var(--border);
  }
</style>
