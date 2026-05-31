<script lang="ts">
  // The carriers identified on a tower (Slice A / #28) — the shared renderer
  // used by BOTH the LeadPage holdings (where a clicked tower lands) and the
  // schema-driven DetailsPanel. One row per ULS licensee: name + callsign
  // (+ license expiry), with a confidence badge (colour + tooltip + the tag
  // word in text/aria so colour is never the only signal). De-dup + ordering
  // are done upstream in #24 — rendered as given. Empty is the COMMON case
  // (most ASR towers have no matched ULS per-site license), so it reads as
  // normal, not an error.
  import { confidenceMeta, type Carrier } from '../lib/carrier';

  let { carriers, compact = false }: { carriers: Carrier[]; compact?: boolean } = $props();
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
          <span class="sub">
            {c.callsign || '—'}{#if c.license_expiry} · exp {c.license_expiry}{/if}
          </span>
        </span>
        <span
          class="badge badge-{m.tone}"
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

  /* Confidence badge — mirrors the DetailsPanel `.tag-*` idiom; hues are the
     Wong colourblind-safe palette (green / amber / gray). The tag word is in
     the badge text + aria-label, so colour is never the only cue. */
  .badge {
    flex-shrink: 0;
    font-size: 10.5px;
    font-weight: 600;
    letter-spacing: 0.02em;
    padding: 2px 8px;
    border-radius: 999px;
    white-space: nowrap;
  }
  .badge-verified {
    background: rgba(0, 158, 115, 0.15);
    color: #006146;
  }
  .badge-likely {
    background: rgba(230, 159, 0, 0.18);
    color: #7a5b00;
  }
  .badge-possible,
  .badge-unknown {
    background: var(--panel-2);
    color: var(--text-2);
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
