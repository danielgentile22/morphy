<script lang="ts">
  import { leads } from '../lib/leads-store.svelte';
  import { STATUSES, STATUS_LABELS, canTransition, type LeadStatus } from '../lib/lead-status';
  import { kindLabel, money, distressText, statusVar, feet } from '../lib/lead-format';
  import { CHANNELS, OUTCOMES, buildAttemptPayload } from '../lib/lead-attempt';
  import type { ContactAttempt, Holding, Structure } from '../lib/leads-api';
  import MiniMap from './MiniMap.svelte';

  let { displayClusterId }: { displayClusterId: string } = $props();

  // (Re)load whenever the routed key changes.
  $effect(() => {
    void leads.loadLead(displayClusterId);
  });

  // Local drafts, seeded once per loaded lead so in-flight edits survive a
  // background refresh (same cluster id ⇒ keep what the user typed).
  let noteDraft = $state('');
  let contactDraft = $state({
    contact_name: '',
    contact_phone: '',
    contact_email: '',
    best_channel: '',
  });
  let attemptForm = $state({ channel: CHANNELS[0] as string, outcome: OUTCOMES[0] as string, occurred_on: '' });
  let loadedFor = '';
  $effect(() => {
    const l = leads.lead;
    if (l && l.owner.display_cluster_id !== loadedFor) {
      noteDraft = l.notes;
      contactDraft = {
        contact_name: l.contact_name,
        contact_phone: l.contact_phone,
        contact_email: l.contact_email,
        best_channel: l.best_channel,
      };
      loadedFor = l.owner.display_cluster_id;
    }
  });

  function towersOf(h: Holding): Structure[] {
    return h.structures.filter((s) => s.type === 'tower');
  }
  function solarOf(h: Holding): Structure[] {
    return h.structures.filter((s) => s.type === 'solar');
  }
  /** Manual attempts vs auto-logged status rows render differently. */
  function isStatusRow(a: ContactAttempt): boolean {
    return a.channel === 'status';
  }

  async function setStatus(s: LeadStatus): Promise<void> {
    const l = leads.lead;
    if (!l || s === l.status) return;
    await leads.saveLead(displayClusterId, { status: s });
  }

  async function saveNote(): Promise<void> {
    await leads.saveLead(displayClusterId, { notes: noteDraft });
  }

  async function saveContact(): Promise<void> {
    await leads.saveLead(displayClusterId, { ...contactDraft });
  }

  async function logAttempt(): Promise<void> {
    const ok = await leads.addAttempt(displayClusterId, buildAttemptPayload(attemptForm));
    if (ok) attemptForm = { ...attemptForm, occurred_on: '' };
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
        <span class="tag x" data-testid="cross-state-badge">cross-state lead</span>
      {/if}
    </header>

    <div class="cols">
      <!-- ── READ: why + holdings ───────────────────────────────────── -->
      <div class="col">
        <section class="card">
          <h3>Why this lead</h3>
          <div class="pills" data-testid="why-pills">
            <div class="pill"><b>{o.score.toFixed(2)}</b><span>score</span></div>
            <div class="pill"><b>{o.parcel_count}</b><span>parcels</span></div>
            <div class="pill"><b>{o.tower_count}</b><span>towers</span></div>
            {#if o.solar_count}
              <div class="pill"><b>{o.solar_count}</b><span>solar</span></div>
            {/if}
            <div class="pill"><b>{money(o.total_assessed_value)}</b><span>assessed</span></div>
            <div class="pill"><b>{feet(l.tallest_tower_height_m)}</b><span>tallest</span></div>
          </div>
          <div class="distress">
            <span class="label">Distress overlays</span>
            <span class={o.distress_tier === 'distressed' ? 'distress-high' : ''}>
              {distressText(o)}
            </span>
          </div>
        </section>

        <section class="card">
          <h3>Holdings · {o.parcel_count} parcels across {o.states.length} state{o.states.length === 1 ? '' : 's'}</h3>
          <MiniMap holdings={l.holdings} />
          {#if l.holdings.length === 0}
            <p class="muted small mt">
              Per-parcel holdings aren’t in the index yet — rebuild it with
              <code>python scripts/preprocess.py --owners-index</code>.
            </p>
          {:else}
            <ul class="holdings" data-testid="holdings">
              {#each l.holdings as h (h.parcel_id + h.state)}
                <li class="holding">
                  <div class="hrow">
                    <b>{h.state} · County {h.county_fips || '—'}</b>
                    <span class="readonly">
                      {money(h.assessed_value)}{#if h.acreage} · {h.acreage} ac{/if}
                    </span>
                  </div>
                  {#if h.land_use}<div class="readonly use">{h.land_use}</div>{/if}
                  {#each towersOf(h) as t (t.asr)}
                    <div class="twr">
                      ▲ Tower ASR {t.asr} — {feet(t.height_m)}{#if t.structure_kind} {t.structure_kind}{/if}{#if t.active === false} (inactive){/if}
                    </div>
                  {/each}
                  {#each solarOf(h) as s (s.id)}
                    <div class="twr">☀ Solar facility{#if s.owner} — {s.owner}{/if}</div>
                  {/each}
                </li>
              {/each}
            </ul>
          {/if}
        </section>
      </div>

      <!-- ── WRITE: status + contact + attempts + notes ─────────────── -->
      <div class="col">
        <section class="card">
          <h3>Status</h3>
          <div class="statusbtns" data-testid="status-selector">
            {#each STATUSES as s (s)}
              <button
                class="sbtn"
                class:on={l.status === s}
                style={l.status === s
                  ? `background:${statusVar(s)};border-color:${statusVar(s)};color:#fff`
                  : ''}
                disabled={!canTransition(l.status, s)}
                data-status={s}
                onclick={() => setStatus(s)}
              >
                {STATUS_LABELS[s]}
              </button>
            {/each}
          </div>
          <p class="ladder muted small">
            New → Researching → Contacted → (Interested → In Business) | Uninterested ·
            status changes are auto-logged below.
          </p>
          {#if leads.saveError}
            <p class="state-msg err" data-testid="save-error">{leads.saveError}</p>
          {/if}
        </section>

        <section class="card">
          <h3>Contact</h3>
          <div class="kv">
            <span class="flabel">Mailing (read-only)</span>
            <span class="readonly" data-testid="mailing-address">
              {#if l.mailing_address}
                {l.mailing_address.addr}{#if l.mailing_address.city}, {l.mailing_address.city}{/if}{#if l.mailing_address.state} {l.mailing_address.state}{/if}
                {l.mailing_address.zip}
              {:else}
                — none on file —
              {/if}
            </span>
          </div>
          <label class="field">
            <span class="flabel">Contact name</span>
            <input data-testid="contact-name" bind:value={contactDraft.contact_name} placeholder="—" />
          </label>
          <label class="field">
            <span class="flabel">Phone</span>
            <input bind:value={contactDraft.contact_phone} placeholder="—" />
          </label>
          <label class="field">
            <span class="flabel">Email</span>
            <input bind:value={contactDraft.contact_email} placeholder="—" />
          </label>
          <label class="field">
            <span class="flabel">Best channel</span>
            <select bind:value={contactDraft.best_channel}>
              <option value="">—</option>
              {#each CHANNELS as c (c)}<option value={c}>{c}</option>{/each}
            </select>
          </label>
          <button class="save" data-testid="save-contact" onclick={saveContact} disabled={leads.saving}>
            {leads.saving ? 'Saving…' : 'Save contact'}
          </button>
        </section>

        <section class="card">
          <h3>Contact attempts</h3>
          <div class="attemptform" data-testid="attempt-form">
            <input
              type="date"
              data-testid="attempt-date"
              bind:value={attemptForm.occurred_on}
              aria-label="Attempt date"
            />
            <select data-testid="attempt-channel" bind:value={attemptForm.channel} aria-label="Channel">
              {#each CHANNELS as c (c)}<option value={c}>{c}</option>{/each}
            </select>
            <select data-testid="attempt-outcome" bind:value={attemptForm.outcome} aria-label="Outcome">
              {#each OUTCOMES as o2 (o2)}<option value={o2}>{o2}</option>{/each}
            </select>
            <button class="sbtn" data-testid="log-attempt" onclick={logAttempt} disabled={leads.saving}>
              + log attempt
            </button>
          </div>
          {#if l.attempts.length === 0}
            <p class="muted small mt">No attempts logged yet.</p>
          {:else}
            <ul class="activity" data-testid="activity">
              {#each l.attempts as a (a.id)}
                <li class:status={isStatusRow(a)}>
                  <span class="muted when">{a.occurred_on}</span>
                  {#if isStatusRow(a)}
                    <span>Status changed</span>
                    <span class="readonly">{a.outcome}</span>
                  {:else}
                    <span>{a.channel}</span>
                    <span class="readonly">{a.outcome}</span>
                  {/if}
                </li>
              {/each}
            </ul>
          {/if}
        </section>

        <section class="card">
          <h3>Notes</h3>
          <textarea
            class="notes"
            data-testid="notes"
            bind:value={noteDraft}
            placeholder="Free-text notes…"
          ></textarea>
          <button class="save" data-testid="save-note" onclick={saveNote} disabled={leads.saving}>
            {leads.saving ? 'Saving…' : 'Save note'}
          </button>
        </section>
      </div>
    </div>
  {/if}
</div>

<style>
  .lead {
    padding: 16px 22px 40px;
    max-width: 1100px;
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
    align-items: start;
  }
  @media (max-width: 860px) {
    .cols {
      grid-template-columns: 1fr;
    }
  }
  .col {
    display: flex;
    flex-direction: column;
    gap: 16px;
    min-width: 0;
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
  .mt {
    margin-top: 10px;
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
    min-width: 60px;
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
  /* holdings */
  .holdings {
    list-style: none;
    margin: 12px 0 0;
    padding: 0;
  }
  .holding {
    padding: 8px 0;
    border-bottom: 1px solid var(--border);
    font-size: 12.5px;
  }
  .hrow {
    display: flex;
    justify-content: space-between;
    gap: 10px;
  }
  .use {
    font-size: 11px;
  }
  .twr {
    margin-top: 3px;
    font-size: 12px;
    color: var(--text-2);
  }
  .readonly {
    color: var(--muted);
  }
  .small {
    font-size: 11.5px;
  }
  .muted {
    color: var(--muted);
  }
  code {
    font-family: var(--mono);
    background: var(--panel-2);
    padding: 1px 5px;
    border-radius: 3px;
    font-size: 11px;
  }
  /* status */
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
  /* contact + forms */
  .kv {
    margin-bottom: 10px;
  }
  .field {
    display: block;
    margin-bottom: 8px;
  }
  .flabel {
    display: block;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--muted);
    margin-bottom: 3px;
  }
  .field input,
  .field select {
    width: 100%;
    font-family: inherit;
    font-size: 13px;
    padding: 7px 9px;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius);
    background: var(--panel);
  }
  .attemptform {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    align-items: center;
  }
  .attemptform input,
  .attemptform select {
    font-family: inherit;
    font-size: 12.5px;
    padding: 6px 8px;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius);
    background: var(--panel);
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
    margin: 12px 0 0;
    padding: 0;
    font-size: 12.5px;
  }
  .activity li {
    display: flex;
    gap: 10px;
    padding: 5px 0;
    border-bottom: 1px solid var(--border);
  }
  .activity li.status {
    color: var(--text-2);
  }
  .activity .when {
    min-width: 84px;
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
</style>
