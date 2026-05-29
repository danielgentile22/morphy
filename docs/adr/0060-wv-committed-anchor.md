# ADR-060: West Virginia elevated to a committed Phase-1 anchor

**Status:** Accepted
**Date:** 2026-05-29
**Pairs with:** ADR-001 (state-level scope), ADR-053 (product phase shift)

## Context

Phase 1 launched with committed anchors AR + MT + FL (NC demoted to a deferred
Phase-1 stretch in the 2026-05-29 audit). The 2026-05-27 50-state pilot review
retro-scored West Virginia (FIPS `54`) against the anchor rubric and ranked it
**#5 of 51 jurisdictions** (OP-weighted composite 6.43) — out-performing every
original anchor under that formula. WV's standout properties:

- **Commercial usability 9/10** — highest in the anchor cohort. WV FOIA §29B-1
  is silent on commercial reuse (no "no resale" clause); no telemarketing surety
  bond; no enacted state privacy law.
- **Free statewide parcels** — SB 588 (2017) mandates a free bulk download of all
  55 counties via WVGISTC / MapWV. The MapWV terms-of-use were reviewed and are
  permissive (free public service; copy/distribute without obligation).
- **100% ARC coverage** — all 55 WV counties are Appalachian, so the ARC distress
  overlay covers the entire state (unique among US states); 11 distressed
  counties, 5 never-above-distressed since 1983.

The code + data were integrated on 2026-05-29 (PR #44): the `wv_parcels` source +
normalizer adapter, and `composite/54` (1,389,855 parcels joined to the national
towers + ARC/HUD/USDA distress; 11 joins, 8 views, 0 warnings; live in the map
app). That work deliberately stopped short of the governance decision — which
this ADR now makes.

## Decision

**West Virginia (54) is a committed Phase-1 anchor**, alongside AR (05), MT (30),
and FL (12). The committed anchor set is now **AR + MT + FL + WV** (four states).
NC (37) remains a deferred Phase-1 stretch.

Scope language follows: every "three committed anchors / 3 anchor states"
reference becomes four, and WV moves from "candidate" to "anchor" in
[SCOPE.md §2](../SCOPE.md), [STATUS.md](../STATUS.md), [README.md](../../README.md),
[CLAUDE.md §7](../../CLAUDE.md), [ROADMAP.md](../ROADMAP.md), and
[GOALS.md](../GOALS.md).

## Consequences

- Slice F's anchor-compose gate now includes WV — already met (`composite/54`
  built and verified 2026-05-29).
- Slice A (carriers) and Slice C (asset enrichment) gates ("anchor states") now
  span four states.
- The Phase-1 outcome bar (co-founder uses the product as his primary daily
  triage tool for 4 consecutive weeks) spans AR + MT + FL + WV.
- **Surface-owner framing.** WV parcels name the *surface* owner; split-estate
  (severed minerals) is the norm in rural WV. Records are surface-only — do not
  conflate with mineral ownership.
- **Outreach compliance is a business-process item, not pipeline code.** WV
  §46A-6F telemarketer registration (60-day-advance) gates residential cold-call;
  the §46A-6F B2B carve-out covers cold-call to LLC business numbers; mail is the
  cleanest channel; the WVSORO political environment warrants outreach-script
  care. None of this is in the data pipeline's scope.
- **No code change is required by this ADR** — the source, adapter, and composite
  already exist (PR #44). This is a scope/governance decision only.

## Alternatives considered

- **Keep WV a candidate (status quo).** Rejected — the data is live and composed,
  WV out-scores the original anchors on the rubric, and "candidate" understates
  its standing. The user elected to commit it.
- **Swap WV in for a weaker anchor (e.g. drop FL).** Rejected — FL remains
  valuable (largest parcel set, distinct market); the set expands, not swaps.
- **Wait for the 4-week outcome-bar usage before committing.** Rejected —
  committing the anchor set is a scope decision, independent of that milestone.
