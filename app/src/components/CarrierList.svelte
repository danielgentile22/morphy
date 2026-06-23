<script lang="ts">
  // The carriers identified on a tower (Slice A / #28) — the shared renderer
  // used by BOTH the LeadPage holdings (where a clicked tower lands) and the
  // schema-driven DetailsPanel. One row per ULS licensee: name + callsign,
  // with a confidence badge (colour + tooltip + the tag word in text/aria so
  // colour is never the only signal). De-dup + ordering
  // are done upstream in #24 — rendered as given. Empty is the COMMON case
  // (most ASR towers have no matched ULS per-site license), so it reads as
  // normal, not an error.
  import { confidenceMeta, type Carrier } from '../lib/carrier';

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
    <span class="none">No carriers identified</span>
    <span class="why">No ULS per-site license matched this tower — common; most towers have none.</span>
  </div>
{:else}
  <ul class="carriers" class:compact data-testid="carrier-list">
    {#each carriers as c, i (c.callsign + '·' + i)}
      {@const m = confidenceMeta(c.confidence_tag)}
      <li class="carrier">
        <span class="who">
          <span class="name">{c.carrier_name || 'Unknown licensee'}</span>
          <span class="sub">{c.callsign || '—'}</span>
        </span>
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
