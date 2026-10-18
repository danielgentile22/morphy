# ADR-060: West Virginia elevated to a committed Phase 1 anchor

**Status:** Accepted
**Date:** 2026-05-29
**Pairs with:** ADR-001 (state-level scope), ADR-053 (product phase shift)

## Context

Phase 1 started with committed anchors AR, MT and FL (NC was demoted to a deferred
Phase 1 stretch in the 2026-05-29 audit). The 2026-05-27 50-state review
scored West Virginia (Federal Information Processing Standards code `54`) against
the anchor rubric and ranked it **5th of 51 jurisdictions** (weighted composite
6.43), ahead of every original anchor under that formula. What stood out:

- **Data reuse terms scored 9/10**, the highest in the anchor cohort. The WV Freedom
  of Information Act (§29B-1) is silent on reuse of released records (no "no resale"
  clause), and WV has no enacted state privacy law.
- **Free statewide parcels.** SB 588 (2017) mandates a free bulk download of all
  55 counties through the WV GIS Technical Center and MapWV. The MapWV terms of use
  were reviewed and are permissive (a free public service; copy and distribute
  without obligation).
- **Full Appalachian Regional Commission (ARC) coverage.** All 55 WV counties are
  Appalachian, so the ARC distress overlay covers the whole state (unique among US
  states): 11 distressed counties, 5 of them never above distressed since 1983.

The code and data were integrated on 2026-05-29: the `wv_parcels` source and
normalizer adapter, and `composite/54` (1,389,855 parcels joined to the national
towers plus the ARC, HUD (Department of Housing and Urban Development) and USDA
(Department of Agriculture) distress overlays; 11 joins, 8 views, 0 warnings; shown
in the map app). That work stopped short of the scope decision, which this ADR makes.

## Decision

**West Virginia (54) is a committed Phase 1 anchor**, alongside AR (05), MT (30)
and FL (12). The committed anchor set is now **AR, MT, FL and WV** (four states).
NC (37) remains a deferred Phase 1 stretch.

Scope language follows: every "three committed anchors" reference becomes four, and
WV moves from "candidate" to "anchor" across the docs. The anchor-state table lives in
[STATUS.md](../STATUS.md).

## Consequences

- Slice F's anchor-compose gate now includes WV. It was already met (`composite/54`
  built and verified on 2026-05-29).
- The Slice A (carriers) and Slice C (asset enrichment) gates on "anchor states" now
  span four states.
- **Surface-owner framing.** WV parcels name the *surface* owner. Split estates
  (severed mineral rights) are the norm in rural WV. Records are surface-only and must
  not be conflated with mineral ownership.
- Contact and telemarketing compliance rules in WV are outside the data pipeline's scope.
- **This ADR requires no code change.** The source, adapter and composite already
  exist. It is a scope decision only.

## Alternatives considered

- **Keep WV a candidate (status quo).** Rejected. The data was composed and shown in
  the app, WV out-scored the original anchors on the rubric, and "candidate" understated
  its standing.
- **Swap WV in for a weaker anchor (for example, drop FL).** Rejected. FL stays useful
  (largest parcel set, distinct market). The set expands rather than swaps.
- **Wait for a period of real usage before committing.** Rejected. Committing the anchor
  set is a scope decision, independent of usage milestones.
