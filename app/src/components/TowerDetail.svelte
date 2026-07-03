<script lang="ts">
  // Tower detail page (UI overhaul P1 / #108, ADR-067; extended round 2).
  //
  // A peek at one antenna: ASR, height, type, carriers, active, parcel,
  // location, score, and the owner as a link — reached from the Explore
  // map/list. Every tower opens, including one with NO resolved landowner
  // (round 2): an *unowned* tower still gets a page showing the basic facts
  // the static tower layer carries, plus an editable panel to fill in owner
  // details + an address manually. Address + archive apply to every antenna.
  //
  // Owned towers load their owner's Lead (the owners index, #105) for the rich
  // facts (carriers, parcel, per-tower score); unowned towers fall back to the
  // static tower-layer feature.
  import { leads } from '../lib/leads-store.svelte';
  import { app } from '../lib/stores.svelte';
  import { feet } from '../lib/lead-format';
  import { leadHash, isUnowned, SECTION_HASH } from '../lib/nav';
  import { archivedAntennas } from '../lib/archived-antennas.svelte';
  import {
    fetchAntenna,
    updateAntenna,
    type AntennaState,
    type Holding,
    type Structure,
  } from '../lib/leads-api';
  import CarrierList from './CarrierList.svelte';
  import LinkedTasks from './LinkedTasks.svelte';

  let { cid, asr }: { cid: string; asr: string } = $props();

  const owned = $derived(!isUnowned(cid));

  // Owned towers load their owner's Lead (rich facts live there).
  $effect(() => {
    if (owned) void leads.loadLead(cid);
  });

  // The tower (by ASR) + its holding, from the owner's footprint (owned only).
  const found = $derived.by((): { tower: Structure; holding: Holding } | null => {
    if (!owned) return null;
    const l = leads.lead;
    if (!l) return null;
    for (const h of l.holdings) {
      for (const s of h.structures) {
        if (s.type === 'tower' && s.asr === asr) return { tower: s, holding: h };
      }
    }
    return null;
  });

  // Basic facts from the static tower layer — always available, and the ONLY
  // source for an unowned tower (or one missing from a stale owner index).
  const pointFeature = $derived(
    app.towerPoints?.features.find((f) => f.properties.asr === asr) ?? null,
  );
  const pointCoords = $derived(
    pointFeature ? (pointFeature.geometry.coordinates as [number, number]) : null,
  );
  // Static tower-layer facts that only ride towers.json (audit M-b/M-c /
  // #208): the build date + the ASR registrant (towerco/carrier — the lease
  // counterparty, NOT the landowner). The owners-index Structure doesn't
  // carry them, so both owned and unowned towers read them from here.
  const staticProps = $derived(pointFeature?.properties ?? null);
  const towerOwnerAddress = $derived.by(() => {
    const p = staticProps;
    if (!p) return null;
    const cityStateZip = [p.tower_owner_city, p.tower_owner_state, p.tower_owner_zip]
      .filter(Boolean)
      .join(' ');
    const parts = [p.tower_owner_street, cityStateZip].filter(Boolean);
    return parts.length ? parts.join(', ') : null;
  });
  const hasTowerOwnerBlock = $derived(
    Boolean(staticProps?.tower_owner || towerOwnerAddress || staticProps?.tower_owner_phone),
  );

  // ── per-antenna manual state (address / manual owner / notes) ─────────────
  let draft = $state({ address: '', owner_name: '', owner_phone: '', owner_email: '', notes: '' });
  let antStatus = $state<'idle' | 'loading' | 'saving' | 'error'>('idle');
  let antError = $state<string | null>(null);
  let saved = $state(false);

  $effect(() => {
    const a = asr;
    antStatus = 'loading';
    saved = false;
    fetchAntenna(a)
      .then((res: AntennaState) => {
        if (a !== asr) return; // a newer tower superseded this load
        draft = {
          address: res.address,
          owner_name: res.owner_name,
          owner_phone: res.owner_phone,
          owner_email: res.owner_email,
          notes: res.notes,
        };
        antStatus = 'idle';
      })
      .catch((e) => {
        if (a !== asr) return;
        antError = e instanceof Error ? e.message : String(e);
        antStatus = 'error';
      });
  });

  const archived = $derived(archivedAntennas.isArchived(asr));

  async function saveDetails(): Promise<void> {
    antStatus = 'saving';
    antError = null;
    saved = false;
    try {
      await updateAntenna(asr, { ...draft });
      saved = true;
      antStatus = 'idle';
    } catch (e) {
      antError = e instanceof Error ? e.message : String(e);
      antStatus = 'error';
    }
  }

  async function toggleArchive(): Promise<void> {
    antError = null;
    try {
      await archivedAntennas.setArchived(asr, !archived);
    } catch (e) {
      antError = e instanceof Error ? e.message : String(e);
    }
  }

  function back(): void {
    location.hash = SECTION_HASH.explore;
  }

  // Pursue (#109): the commit action that leaves Explore (owned towers only).
  const worked = $derived(owned && leads.lead != null && leads.lead.status !== 'new');
  async function pursue(): Promise<void> {
    const ok = await leads.pursue(cid, asr);
    if (ok) location.hash = leadHash(cid);
  }
</script>

<div class="tower" data-testid="tower-detail">
  <button class="back" onclick={back}>‹ back to Explore</button>

  {#if owned && leads.leadStatus === 'loading' && !found}
    <p class="muted">Loading tower…</p>
  {:else}
    {@const richTower = found?.tower ?? null}
    <header class="head">
      <h1>Tower {asr}</h1>
      {#if archived}<span class="tag archived" data-testid="archived-tag">archived</span>{/if}
      {#if richTower?.active === false}<span class="tag inactive">inactive</span>{/if}
      {#if richTower?.score != null}<span class="tag score" data-testid="tower-score">score {richTower.score.toFixed(2)}</span>{/if}
    </header>

    {#if owned && leads.lead}
      <p class="owner-line">
        Owned by
        <a class="ownerlink" href={leadHash(cid)} data-testid="tower-owner-link">{leads.lead.owner.owner_name}</a>
        · {leads.lead.owner.states.join('/')}
      </p>
      <div class="actions">
        {#if worked}
          <a class="btn btn-secondary open" href={leadHash(cid)} data-testid="open-in-leads">Open in Leads →</a>
          <span class="worked-note">already a lead ({leads.lead.status})</span>
        {:else}
          <button class="btn btn-primary pursue" data-testid="pursue" onclick={pursue} disabled={leads.saving}>
            {leads.saving ? 'Pursuing…' : 'Pursue this owner'}
          </button>
          <span class="worked-note">starts a Lead (all their towers); records this antenna as the trigger</span>
        {/if}
      </div>
      {#if leads.saveError}<p class="err" data-testid="pursue-error">{leads.saveError}</p>{/if}
    {:else}
      <p class="owner-line" data-testid="no-owner-note">
        {owned && leads.leadStatus === 'error'
          ? 'Owner record unavailable — showing the basic facts on file. Add details below.'
          : 'No landowner on file for this tower — add owner details below if you find them.'}
      </p>
    {/if}

    <section class="card">
      <h3>Tower</h3>
      {#if richTower}
        {@const t = richTower}
        <dl class="kv">
          <dt>ASR</dt><dd>{t.asr}</dd>
          <dt>Height</dt><dd>{feet(t.height_m ?? null)}</dd>
          <dt>Structure</dt><dd>{t.structure_kind || '—'}</dd>
          <dt>Active</dt><dd>{t.active == null ? '—' : t.active ? 'yes' : 'no'}</dd>
          <dt>Built</dt><dd data-testid="tower-date-built">{staticProps?.date_built ?? '—'}</dd>
          <dt>Coordinates</dt>
          <dd>{t.lat != null && t.lon != null ? `${t.lat.toFixed(5)}, ${t.lon.toFixed(5)}` : '—'}</dd>
          <dt>Score</dt><dd>{t.score != null ? t.score.toFixed(2) : '—'}</dd>
        </dl>
      {:else if pointFeature}
        {@const p = pointFeature.properties}
        <dl class="kv">
          <dt>ASR</dt><dd>{p.asr}</dd>
          <dt>Height</dt><dd>{p.height_m != null ? feet(p.height_m) : '—'}</dd>
          <dt>State</dt><dd>{p.state || '—'}</dd>
          <dt>Active</dt><dd>{p.active ? 'yes' : 'no'}</dd>
          <dt>Built</dt><dd data-testid="tower-date-built">{p.date_built ?? '—'}</dd>
          <dt>Coordinates</dt>
          <dd>{pointCoords ? `${pointCoords[1].toFixed(5)}, ${pointCoords[0].toFixed(5)}` : '—'}</dd>
        </dl>
      {:else}
        <p class="muted" data-testid="tower-facts-missing">
          {app.towersStatus === 'loading'
            ? 'Loading tower data…'
            : `No data on file for ASR ${asr}.`}
        </p>
      {/if}
    </section>

    <!-- The ASR registrant's contact block (audit M-b / #208): the towerco /
         carrier that registered the structure — the lease counterparty. Kept
         visually distinct from the landowner above. FCC-sourced towers carry
         it on ~99% of rows; FAA-sourced ones have none, so the card hides. -->
    {#if hasTowerOwnerBlock}
      {@const p = staticProps!}
      <section class="card" data-testid="tower-owner-card">
        <h3>Tower owner (ASR)</h3>
        <dl class="kv">
          <dt>Name</dt><dd data-testid="tower-owner-name">{p.tower_owner ?? '—'}</dd>
          <dt>Address</dt><dd data-testid="tower-owner-address">{towerOwnerAddress ?? '—'}</dd>
          <dt>Phone</dt><dd data-testid="tower-owner-phone">{p.tower_owner_phone ?? '—'}</dd>
        </dl>
        <p class="worked-note">The FCC ASR registrant — who to negotiate with, not the landowner.</p>
      </section>
    {/if}

    {#if found}
      {@const t = found.tower}
      {@const h = found.holding}
      <section class="card">
        <h3>Carriers</h3>
        <CarrierList carriers={t.carriers ?? []} />
      </section>

      <section class="card">
        <h3>Parcel</h3>
        <dl class="kv">
          <dt>State</dt><dd>{h.state}</dd>
          <dt>County FIPS</dt><dd>{h.county_fips || '—'}</dd>
          <dt>Land use</dt><dd>{h.land_use || '—'}</dd>
          <dt>Market</dt>
          <dd>{h.assessed_value ? `$${h.assessed_value.toLocaleString()}` : '—'}</dd>
          <dt>Assessed (statutory)</dt>
          <dd>
            {h.statutory_assessed_value ? `$${h.statutory_assessed_value.toLocaleString()}` : '—'}
          </dd>
          <dt>Acreage</dt><dd>{h.acreage != null ? `${h.acreage} ac` : '—'}</dd>
          <dt>Parcel ID</dt><dd>{h.parcel_id}</dd>
        </dl>
      </section>
    {/if}

    <!-- Editable manual layer (round 2): an address on every antenna; owner
         details too when the tower has no resolved landowner. -->
    <section class="card" data-testid="manual-card">
      <h3>Manual details</h3>
      <div class="form">
        <label for="m-address">Address</label>
        <input
          id="m-address"
          type="text"
          bind:value={draft.address}
          placeholder="street address (if known)"
          data-testid="manual-address"
        />

        {#if !owned}
          <label for="m-owner">Owner name</label>
          <input
            id="m-owner"
            type="text"
            bind:value={draft.owner_name}
            placeholder="landowner (if found)"
            data-testid="manual-owner-name"
          />
          <label for="m-phone">Owner phone</label>
          <input id="m-phone" type="text" bind:value={draft.owner_phone} data-testid="manual-owner-phone" />
          <label for="m-email">Owner email</label>
          <input id="m-email" type="email" bind:value={draft.owner_email} data-testid="manual-owner-email" />
        {/if}

        <label for="m-notes">Notes</label>
        <textarea id="m-notes" rows="3" bind:value={draft.notes} data-testid="manual-notes"></textarea>

        <div class="form-actions">
          <button
            class="btn btn-primary save"
            onclick={saveDetails}
            disabled={antStatus === 'saving' || antStatus === 'loading'}
            data-testid="manual-save"
          >
            {antStatus === 'saving' ? 'Saving…' : 'Save details'}
          </button>
          {#if saved}<span class="ok" data-testid="manual-saved">Saved ✓</span>{/if}
        </div>
        {#if antError}<p class="err" data-testid="manual-error">{antError}</p>{/if}
      </div>
    </section>

    <!-- Archive (round 2): park an antenna that's not of interest — it drops
         off the Explore map + list until un-archived (recoverable). -->
    <section class="card archive-card">
      <button class="btn btn-secondary archive" onclick={toggleArchive} data-testid="archive-toggle">
        {archived ? 'Un-archive antenna' : 'Archive antenna'}
      </button>
      <span class="worked-note">
        {archived
          ? 'Hidden from the Explore map + list. Un-archive to bring it back.'
          : 'Hides it from the Explore map + list (recoverable any time).'}
      </span>
    </section>

    <!-- Tower-linked tasks (#110). -->
    <LinkedTasks query={`tower=${encodeURIComponent(asr)}`} heading="Tasks for this tower" />
  {/if}
</div>

<style>
  .tower {
    height: 100%;
    overflow-y: auto;
    padding: 16px 22px 40px;
    max-width: 720px;
  }
  .back {
    font-size: 12.5px;
    margin-bottom: 12px;
    background: none;
    border: none;
    padding: 0;
    color: var(--accent);
  }
  .head {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
    margin-bottom: 6px;
  }
  .head h1 {
    font-size: 20px;
  }
  .tag {
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 999px;
    border: 1px solid var(--border);
    background: var(--panel-2);
    color: var(--text-2);
  }
  .tag.score {
    color: var(--accent);
    border-color: var(--accent);
  }
  .tag.inactive {
    color: var(--muted);
  }
  .tag.archived {
    color: var(--color-warning);
    background: var(--color-warning-soft);
    border-color: transparent;
  }
  .owner-line {
    font-size: 13px;
    color: var(--text-2);
    margin-bottom: 10px;
  }
  .actions {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
    margin-bottom: 16px;
  }
  .btn {
    padding: 8px 16px;
    font-size: 13px;
    font-weight: 600;
    border-radius: var(--radius);
    border: 1px solid var(--accent);
    cursor: pointer;
    text-decoration: none;
  }
  .btn.pursue {
    background: var(--accent);
    color: #fff;
  }
  .btn.pursue:disabled {
    opacity: 0.6;
  }
  .btn.open {
    background: var(--panel);
    color: var(--accent);
  }
  .worked-note {
    font-size: 11.5px;
    color: var(--muted);
  }
  .ownerlink {
    color: var(--accent);
    text-decoration: none;
  }
  .ownerlink:hover {
    text-decoration: underline;
  }
  .card {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 14px 16px;
    margin-bottom: 14px;
  }
  .card h3 {
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
    margin-bottom: 10px;
  }
  .kv {
    display: grid;
    grid-template-columns: 120px 1fr;
    gap: 6px 12px;
    margin: 0;
    font-size: 13px;
  }
  .kv dt {
    color: var(--muted);
  }
  .kv dd {
    margin: 0;
  }
  /* Manual-details form. */
  .form {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .form label {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--muted);
    margin-top: 6px;
  }
  .form input,
  .form textarea {
    padding: 7px 9px;
    font-size: 13px;
    font-family: inherit;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius);
    background: var(--panel);
  }
  .form textarea {
    resize: vertical;
  }
  .form-actions {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-top: 10px;
  }
  .btn.save {
    background: var(--accent);
    color: #fff;
  }
  .btn.save:disabled {
    opacity: 0.6;
  }
  .ok {
    font-size: 12px;
    color: var(--color-success);
  }
  .archive-card {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
  }
  .btn.archive {
    background: var(--panel);
    color: var(--text);
    border-color: var(--border-strong);
  }
  .muted {
    color: var(--muted);
    font-size: 13px;
  }
  .err {
    color: var(--danger);
    font-size: 13px;
  }
</style>
