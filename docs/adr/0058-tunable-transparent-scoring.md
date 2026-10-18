# ADR-058: Tunable and transparent interestingness scoring

**Status:** Accepted. Default weights reweighted by [ADR-073](0073-interestingness-reweight.md); the framework stands.
**Date:** 2026-05-25
**Pairs with:** ADR-053, ADR-056

## Context

`scripts/preprocess/score.py` computes `interestingness_score` per parcel as a weighted sum of components: infrastructure presence, distress overlays, Appalachian Regional Commission (ARC) county tier, owner kind (LLC or trust), and owner cluster size. The weights are hardcoded, and the score is opaque to consumers: `interestingness_components` is computed, but the map app does not show it.

For the product (ADR-053), scoring is the **central ranking mechanism** for narrowing 2M+ parcels to about 50 leads a week. The status quo has two problems:

1. **The score has no signal for the factors that matter most in triage:** carrier count, lease expiry, vendor concentration, and rent versus comparables. None of these have data yet. They arrive in Slice A (carriers) and Slice D (leases).
2. **Only the developer controls the weights.** If the analyst learns that expiring leases with 4+ carriers are the best targets, the only route is asking the developer to change `score.py` and re-run the whole pipeline.

## Decision

Scoring becomes **tunable and transparent** in the map app (Slice C):

- **The score moves from baked-into-parquet to computed on demand in the client.** Parquet stores the *components* (boolean and int fields). DuckDB-WASM computes `weights × components → score` live in the browser when the weights change.
- **The analyst adjusts weights live** with UI sliders. The ranking re-orders, map fades update, and the top-50 list reshuffles.
- **Saved scoring profiles:** named weight presets (for example "distress-first" or "carrier-and-expiry"). They live in localStorage before Slice D+E, then move to the backend, tied to the user account.
- **A per-parcel component breakdown** shows in the lead-detail panel ("scored 0.65 = 0.30 infra + 0.20 distress + 0.15 county tier").
- **The current hardcoded weights become the default profile**, so there is no migration.
- **After Slice D+E** (lease documents, carriers, vendor), new signals plug into the same framework: `months_to_expiry`, `rent_vs_comp`, `carrier_count`, `has_lease_on_file`, and `vendor` (a weight for vendors known to be difficult). No scoring redesign is needed then.
- **The cluster-score rollup** (ADR-056) is tunable in the same UI: `max(parcel_scores) + α · log(parcel_count)`, with α defaulting to 0.1.

## Consequences

- Map app v2 already has DuckDB-WASM and the components column. The UI work is sliders, live recompute, and profile persistence.
- Tunable scoring has no backend dependency; it runs fully in the client. Slice C can ship before Slice D+E stands up the backend, and profile persistence moves to the backend in Slice D+E.
- The developer's role becomes exposing new signals as columns and setting reasonable defaults. The analyst owns weight tuning.

## Alternatives considered

- **Status quo (hardcoded, opaque).** Every weight change depends on the developer. Rejected.
- **Transparent but not tunable** (show the component breakdown only). A half-measure: the analyst still cannot experiment. Rejected.

## Amendment (2026-06-06): UI overhaul

The UI overhaul (plan decision D4, shipped; the plan doc was retired and lives in git
history) extends this ADR. The core stands: tunable, transparent, client-side over
DuckDB-WASM, named saved configs, and the original weights as the default. The refinements:

- **Tower grain.** Scoring was specified per **parcel**. Explore (ADR-067) ranks
  **towers**, so the same tunable framework now also produces a **per-tower** score.
  The base is the tower's underlying parcel score, and tower signals (height, carrier
  count, active, vendor) join the feature menu. Owner ranking is an aggregate
  (default `max`) of the owner's tower scores under the active config.
- **Terminology.** The canonical term is **scoring preset** ([GLOSSARY.md](../../GLOSSARY.md)).
  This ADR's "saved scoring profiles" and "named weight presets" mean the same thing.
  "Profile" is now an alias to avoid.
- **Storage.** Presets persist to a **tenant-shared** `scoring_preset` table (the
  team is one tenant). This supersedes the "localStorage, then tied to the user account" note above.
- **Not built.** An **ML-learned** weighting (learning from outcomes which towers convert)
  and **asset-level conversion analytics** (Stats) were expected to feed this later.
  Both were out of scope for the first tunable cut and were never built.

Delivered as **Phase 4** of the overhaul (after the shell, Tasks, and Dashboard
views), not the original Slice C.
