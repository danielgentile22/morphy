<script lang="ts">
  import { leads } from '../lib/leads-store.svelte';
  import { filterModel } from '../lib/filter-model.svelte';
  import { STATUSES, STATUS_LABELS, canTransition, type LeadStatus } from '../lib/lead-status';
  import { kindLabel, money, distressText, statusVar, statusGlyph, feet } from '../lib/lead-format';
  import {
    CHANNELS,
    OUTCOMES,
    REPLY_OUTCOMES,
    buildAttemptPayload,
  } from '../lib/lead-attempt';
  import type { ContactAttempt, Holding, Structure } from '../lib/leads-api';
  import type { OwnerFilterRecord } from '../lib/owners-filter-index';
  import { SECTION_HASH, towerHash } from '../lib/nav';
  import MiniMap from './MiniMap.svelte';
  import CarrierList from './CarrierList.svelte';
  import LinkedTasks from './LinkedTasks.svelte';

  let { displayClusterId }: { displayClusterId: string } = $props();

  // (Re)load whenever the routed key changes.
  $effect(() => {
    void leads.loadLead(displayClusterId);
  });

  // The slim owners index powers the merge picker's owner search (idempotent).
  $effect(() => {
    void filterModel.load();
  });

  // ── merge / split (Slice 7 / #53) ───────────────────────────────────────
  let mergeTerm = $state('');
  // Search hits, minus this owner and any already-merged-in cluster.
  let mergeHits = $derived.by((): OwnerFilterRecord[] => {
    const l = leads.lead;
    if (!l || mergeTerm.trim().length < 2) return [];
    const exclude = new Set([
      l.owner.display_cluster_id,
      ...l.merged_members.map((m) => m.display_cluster_id),
    ]);
    return filterModel.searchOwners(mergeTerm, 8).filter((o) => !exclude.has(o.display_cluster_id));
  });

  async function mergeIn(sourceClusterId: string): Promise<void> {
    const ok = await leads.mergeOwner(displayClusterId, sourceClusterId);
    if (ok) mergeTerm = '';
  }
  async function splitOut(sourceClusterId: string): Promise<void> {
    await leads.splitOwner(displayClusterId, sourceClusterId);
  }

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
  let replyForm = $state({
    channel: CHANNELS[0] as string,
    outcome: REPLY_OUTCOMES[0] as string,
    occurred_on: '',
  });
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
    // De-dup by ASR: the same tower can land on duplicate parcel rows within a
    // holding, which would collide the keyed {#each} (Svelte throws on dup keys).
    const byAsr = new Map<string, Structure>();
    for (const s of h.structures) {
      if (s.type !== 'tower') continue;
      const k = s.asr ?? '';
      if (!byAsr.has(k)) byAsr.set(k, s);
    }
    return [...byAsr.values()];
  }
  function solarOf(h: Holding): Structure[] {
    return h.structures.filter((s) => s.type === 'solar');
  }

  // Owner's towers, ranked + filterable (#108, ADR-067): every tower across
  // the owner's holdings, each with its per-tower score (#105), sorted by
  // score desc, narrowed by an active-only toggle + an ASR search.
  let towerFilter = $state({ activeOnly: false, q: '' });
  const rankedOwnerTowers = $derived.by(() => {
    const l = leads.lead;
    if (!l) return [];
    // De-dup by ASR across ALL holdings: the same tower (ASR) can appear under
    // multiple parcels of one owner (common for carrier/utility portfolios),
    // which would both flood the list and collide the keyed {#each} (Svelte
    // throws on duplicate keys, crashing the page). Keep one row per ASR.
    const byAsr = new Map<string, Structure & { state: string; county_fips: string }>();
    for (const h of l.holdings) {
      for (const s of h.structures) {
        if (s.type !== 'tower') continue;
        const k = s.asr ?? '';
        if (!byAsr.has(k)) byAsr.set(k, { ...s, state: h.state, county_fips: h.county_fips });
      }
    }
    let towers = [...byAsr.values()];
    if (towerFilter.activeOnly) towers = towers.filter((t) => t.active === true);
    const q = towerFilter.q.trim().toLowerCase();
    if (q) towers = towers.filter((t) => (t.asr ?? '').toLowerCase().includes(q));
    return towers.sort((a, b) => (b.score ?? -Infinity) - (a.score ?? -Infinity));
  });
  function openTower(asr: string | null | undefined): void {
    const l = leads.lead;
    if (l && asr) location.hash = towerHash(l.owner.display_cluster_id, asr);
  }
  /** Manual attempts vs auto-logged status rows render differently. */
  function isStatusRow(a: ContactAttempt): boolean {
    return a.channel === 'status';
  }
  /** A reply is an inbound activity event (#106). */
  function isReply(a: ContactAttempt): boolean {
    return a.direction === 'inbound';
  }
  /** A trigger flag from Explore (#109) — channel='flag', outcome=ASR. */
  function isFlag(a: ContactAttempt): boolean {
    return a.channel === 'flag';
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

  /** Log a reply — an inbound activity event (#106). Distinct from an outbound
   *  touch and never changes the Lead's status. */
  async function logReply(): Promise<void> {
    const ok = await leads.addAttempt(displayClusterId, buildAttemptPayload(replyForm, 'inbound'));
    if (ok) replyForm = { ...replyForm, occurred_on: '' };
  }

  function back(): void {
    // Candidates folded into Explore (#104); return to the discovery surface.
    location.hash = SECTION_HASH.explore;
  }
</script>

<div class="lead" data-testid="lead-page">
  <button class="back" onclick={back}>‹ back to Explore</button>

  {#if leads.leadStatus === 'loading'}
    <p class="state-msg">Loading lead…</p>
  {:else if leads.leadStatus === 'error'}
    <p class="state-msg err" data-testid="lead-error">{leads.leadError}</p>
  {:else if leads.lead}
    {@const l = leads.lead}
    {@const o = l.owner}
    <header class="head">
      <span class="dot" style="background:{statusVar(l.status)}"></span>
      <span class="cb-cue" aria-hidden="true">{statusGlyph(l.status)}</span>
      <h1>{o.owner_name}</h1>
      <span class="tag">{kindLabel(o.owner_kind)}</span>
      {#each o.states as s (s)}
        <span class="tag state">{s}</span>
      {/each}
      {#if o.cross_state}
        <span class="tag x" data-testid="cross-state-badge">cross-state lead</span>
      {/if}
      {#if o.trigger_asr}
        <span class="tag trigger" data-testid="trigger-badge">⚑ flagged from ASR {o.trigger_asr}</span>
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
              <!-- Key includes the index: the same parcel_id can appear on more
                   than one holding row (duplicate FDOR NAL parcel rows), which
                   would collide a (parcel_id+state) key and crash the page. The
                   list is static (never filtered/reordered), so the index is a
                   stable disambiguator. -->
              {#each l.holdings as h, hi (h.parcel_id + '|' + h.state + '|' + hi)}
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
                    <div class="carriers-wrap">
                      <CarrierList carriers={t.carriers ?? []} compact />
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

        <!-- Owner's towers, ranked + filterable (#108, ADR-067). -->
        {#if rankedOwnerTowers.length > 0 || towerFilter.activeOnly || towerFilter.q}
          <section class="card" data-testid="owner-towers">
            <h3>Towers · ranked</h3>
            <div class="towerfilter">
              <input
                class="tsearch"
                data-testid="owner-tower-search"
                bind:value={towerFilter.q}
                placeholder="Filter by ASR…"
                aria-label="Filter towers by ASR"
              />
              <label class="activeonly">
                <input type="checkbox" bind:checked={towerFilter.activeOnly} />
                active only
              </label>
            </div>
            {#if rankedOwnerTowers.length === 0}
              <p class="muted small mt">No towers match.</p>
            {:else}
              <ul class="ranked-towers" data-testid="ranked-towers">
                {#each rankedOwnerTowers as t (t.asr)}
                  <li>
                    <button class="tower-row" data-testid="ranked-tower-row" onclick={() => openTower(t.asr)}>
                      <span class="tscore">{t.score != null ? t.score.toFixed(2) : '—'}</span>
                      <span class="tasr">ASR {t.asr}</span>
                      <span class="readonly small">
                        {t.state} · {feet(t.height_m ?? null)}{#if t.active === false} · inactive{/if}
                      </span>
                    </button>
                  </li>
                {/each}
              </ul>
            {/if}
          </section>
        {/if}
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
                <span class="cb-cue" aria-hidden="true">{statusGlyph(s)}</span>
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
          <h3>Activity</h3>
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
              + log touch
            </button>
          </div>
          <!-- Log reply: an inbound event (#106) — what the owner said back. -->
          <div class="attemptform reply" data-testid="reply-form">
            <input
              type="date"
              data-testid="reply-date"
              bind:value={replyForm.occurred_on}
              aria-label="Reply date"
            />
            <select data-testid="reply-channel" bind:value={replyForm.channel} aria-label="Reply channel">
              {#each CHANNELS as c (c)}<option value={c}>{c}</option>{/each}
            </select>
            <select data-testid="reply-outcome" bind:value={replyForm.outcome} aria-label="Reply outcome">
              {#each REPLY_OUTCOMES as o2 (o2)}<option value={o2}>{o2}</option>{/each}
            </select>
            <button class="sbtn reply-btn" data-testid="log-reply" onclick={logReply} disabled={leads.saving}>
              ↩ log reply
            </button>
          </div>
          {#if l.attempts.length === 0}
            <p class="muted small mt">No activity logged yet.</p>
          {:else}
            <ul class="activity" data-testid="activity">
              {#each l.attempts as a (a.id)}
                <li class:status={isStatusRow(a) || isFlag(a)} class:inbound={isReply(a)} data-direction={a.direction ?? 'outbound'}>
                  <span class="muted when">{a.occurred_on}</span>
                  {#if isFlag(a)}
                    <span data-testid="flag-row">⚑ Flagged from ASR {a.outcome}</span>
                    <span class="readonly">from Explore</span>
                  {:else if isStatusRow(a)}
                    <span>Status changed</span>
                    <span class="readonly">{a.outcome}</span>
                  {:else if isReply(a)}
                    <span data-testid="reply-row">↩ Reply · {a.channel}</span>
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

        <!-- Owner-linked tasks (#110). -->
        <LinkedTasks query={`lead=${encodeURIComponent(displayClusterId)}`} heading="Tasks for this owner" />

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

        <!-- ── Owner identity: manual merge / split (Slice 7 / #53) ──────── -->
        <section class="card" data-testid="merge-card">
          <h3>Owner identity</h3>
          <p class="muted small">
            Auto-clustering errs toward <em>not</em> merging. If this landowner is
            split across clusters, merge them; if two distinct owners were grouped,
            split one off.
          </p>

          {#if l.merged_members.length}
            <ul class="merged" data-testid="merged-members">
              {#each l.merged_members as mm (mm.display_cluster_id)}
                <li>
                  <span class="readonly">{mm.owner_name || mm.display_cluster_id}</span>
                  <button
                    class="sbtn"
                    data-testid="split-{mm.display_cluster_id}"
                    onclick={() => splitOut(mm.display_cluster_id)}
                    disabled={leads.saving}
                  >
                    split off
                  </button>
                </li>
              {/each}
            </ul>
          {/if}

          <label class="field mt">
            <span class="flabel">Merge another owner into this lead</span>
            <input
              data-testid="merge-search"
              bind:value={mergeTerm}
              placeholder="Search owner name…"
              autocomplete="off"
            />
          </label>
          {#if mergeHits.length}
            <ul class="merge-hits" data-testid="merge-hits">
              {#each mergeHits as h (h.display_cluster_id)}
                <li>
                  <button
                    class="hit"
                    data-testid="merge-pick-{h.display_cluster_id}"
                    onclick={() => mergeIn(h.display_cluster_id)}
                    disabled={leads.saving}
                  >
                    <b>{h.owner_name}</b>
                    <span class="readonly small">
                      {h.states.join(', ')} · {h.tower_count} tower{h.tower_count === 1 ? '' : 's'}
                    </span>
                  </button>
                </li>
              {/each}
            </ul>
          {:else if mergeTerm.trim().length >= 2}
            <p class="muted small mt">No other owners match “{mergeTerm}”.</p>
          {/if}
        </section>
      </div>
    </div>
  {/if}
</div>

<style>
  .lead {
    height: 100%;
    overflow-y: auto;
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
  .tag.trigger {
    background: #fff4e6;
    border-color: #f0d2a8;
    color: #9a5b00;
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
  /* Carriers sit indented under their tower row. */
  .carriers-wrap {
    margin: 1px 0 4px 14px;
  }
  /* Owner's ranked + filterable towers (#108). */
  .towerfilter {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 8px;
  }
  .tsearch {
    flex: 1;
    font: inherit;
    font-size: 12.5px;
    padding: 5px 8px;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius);
    background: var(--panel);
  }
  .activeonly {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 12px;
    color: var(--text-2);
    white-space: nowrap;
  }
  .ranked-towers {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  .ranked-towers li {
    border-bottom: 1px solid var(--border);
  }
  .tower-row {
    display: flex;
    align-items: baseline;
    gap: 10px;
    width: 100%;
    text-align: left;
    background: none;
    border: none;
    padding: 7px 2px;
    font: inherit;
    cursor: pointer;
  }
  .tower-row:hover {
    background: var(--panel-2);
  }
  .tscore {
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    min-width: 36px;
    color: var(--accent);
  }
  .tasr {
    font-size: 13px;
    font-weight: 600;
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
  /* Inbound replies stand out — they're the events that need attention. */
  .activity li.inbound {
    font-weight: 600;
  }
  .activity li.inbound span:nth-child(2) {
    color: var(--accent);
  }
  .activity .when {
    min-width: 84px;
  }
  .attemptform.reply {
    margin-top: 8px;
  }
  .reply-btn {
    border-color: var(--accent);
    color: var(--accent);
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
  /* merge / split */
  .merged {
    list-style: none;
    margin: 10px 0 0;
    padding: 0;
    font-size: 12.5px;
  }
  .merged li {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    padding: 5px 0;
    border-bottom: 1px solid var(--border);
  }
  .merge-hits {
    list-style: none;
    margin: 6px 0 0;
    padding: 0;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: hidden;
  }
  .merge-hits li + li {
    border-top: 1px solid var(--border);
  }
  .hit {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 1px;
    width: 100%;
    text-align: left;
    background: var(--panel);
    border: none;
    padding: 7px 10px;
    font-size: 12.5px;
  }
  .hit:hover:not(:disabled) {
    background: var(--panel-2);
  }
  .hit:disabled {
    opacity: 0.5;
  }
</style>
