<script lang="ts">
  // The carriers licensed on a tower (Slice A / #28) — the shared renderer
  // used by BOTH the LeadPage holdings (where a clicked tower lands) and the
  // schema-driven DetailsPanel. One row per ULS licensee: name + callsign,
  // with a confidence badge (colour + tooltip + the tag word in text/aria so
  // colour is never the only signal). De-dup + ordering are done upstream in
  // #24 — rendered as given. Empty is the COMMON case (most ASR towers have no
  // overlapping FCC spectrum license), so it reads as normal, not an error.
  //
  // A ULS license is a spectrum AUTHORIZATION over an area, not proof of a
  // rent-paying tenant (audit MACRO-1 / ADR-074) — a one-line disclaimer under
  // the list keeps a badge from being misread as a confirmed tenant.
  import { confidenceMeta, isInactiveLicense, inactiveLicenseLabel, type Carrier } from '../lib/carrier';

  let { carriers, compact = false }: { carriers: Carrier[]; compact?: boolean } = $props();

  // Confidence tone → Halo chip tone. The label text + aria-label always ride
  // along (see below), so colour is never the only signal.
  const BADGE_TONE: Record<string, 'success' | 'warning' | 'neutral'> = {
    verified: 'success',
    likely: 'warning',
    possible: 'neutral',
    unknown: 'neutral',
  };
</script>

{#if carriers.length === 0}
  <div class="carriers empty" class:compact data-testid="carrier-list">
    <span class="none">No carrier licensed here</span>
    <span class="why">No FCC spectrum license overlaps this tower. That is common: most towers show none.</span>
  </div>
{:else}
  <ul class="carriers" class:compact data-testid="carrier-list">
    {#each carriers as c, i (c.callsign + '·' + i)}
      {@const m = confidenceMeta(c.confidence_tag)}
      {@const dead = isInactiveLicense(c)}
      <li class="carrier" class:dead>
        <span class="who">
          <span class="name">{c.carrier_name || 'Unknown licensee'}</span>
          <span class="sub">{c.callsign || '—'}</span>
        </span>
        <!-- A cancelled/expired license must not read as a live carrier
             (audit M-l): a danger chip names the status, and the row dims. -->
        {#if dead}
          <span
            class="chip"
            data-tone="danger"
            data-license-status={c.license_status}
            title="This ULS license is {inactiveLicenseLabel(c).toLowerCase()}, not a live authorization"
            aria-label="License {inactiveLicenseLabel(c)}. Not a live authorization."
          >
            {inactiveLicenseLabel(c)}
          </span>
        {/if}
        <span
          class="chip"
          data-tone={BADGE_TONE[m.tone] ?? 'neutral'}
          data-confidence={c.confidence_tag}
          title={m.tooltip}
          aria-label="Confidence: {m.label}. {m.tooltip}"
        >
          {m.label}
        </span>
      </li>
    {/each}
  </ul>
  <!-- Honest framing (audit MACRO-1 / ADR-074): a ULS license authorizes
       spectrum over this tower's area — it is NOT proof of a rent-paying
       tenant. Shown once per list (skipped in the dense compact holdings). -->
  {#if !compact}
    <p class="disclaimer" data-testid="carrier-disclaimer">
      Licensed in this area: holds FCC spectrum overlapping this tower, not a confirmed tenant.
    </p>
  {/if}
{/if}

<style>
  .carriers {
    list-style: none;
    margin: 4px 0 0;
    padding: 0;
  }
  .carrier {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    padding: 4px 0;
    border-bottom: 1px dotted var(--border);
    font-size: 12.5px;
  }
  .carrier:last-child {
    border-bottom: none;
  }
  .who {
    display: flex;
    flex-direction: column;
    gap: 1px;
    min-width: 0;
  }
  .name {
    font-weight: 500;
    word-break: break-word;
  }
  .sub {
    font-size: 11px;
    color: var(--muted);
    font-variant-numeric: tabular-nums;
  }

  /* Confidence badge renders as a Halo signal chip (tone in BADGE_TONE). The
     tag word is in the chip text + aria-label, so colour is never the only
     cue — stays colourblind-safe. */
  .chip {
    flex-shrink: 0;
  }

  /* A dead license dims the row — the status chip carries the words, the
     dimming is only reinforcement (never the sole signal). */
  .carrier.dead .who {
    opacity: 0.55;
  }

  .empty {
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 6px 0;
  }
  .none {
    font-size: 12.5px;
    color: var(--text-2);
  }
  .why {
    font-size: 11px;
    color: var(--muted);
  }

  /* The authorization-not-tenancy framing (ADR-074) — quiet, but always
     present so a badge is never misread as a confirmed tenant. */
  .disclaimer {
    margin: 6px 0 0;
    font-size: 11px;
    font-style: italic;
    color: var(--muted);
    line-height: 1.35;
  }

  /* Compact variant for the dense LeadPage holdings list. */
  .compact .carrier {
    padding: 2px 0;
    font-size: 12px;
  }
  .compact.empty {
    padding: 2px 0;
  }
  .compact .none {
    font-size: 12px;
  }
</style>
