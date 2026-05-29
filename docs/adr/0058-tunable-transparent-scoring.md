# ADR-058: Tunable + transparent interestingness scoring

**Status:** Accepted
**Date:** 2026-05-25
**Pairs with:** ADR-053, ADR-056

## Context

`scripts/preprocess/score.py` computes `interestingness_score` per parcel as a weighted sum of components: infrastructure presence, distress overlays, ARC county tier, owner kind (LLC/trust), owner cluster size. Weights are hardcoded; the score is opaque to consumers — `interestingness_components` is computed but the map app doesn't surface it.

For the product (ADR-053), scoring is the **central ranking mechanism** the co-founder uses to triage from 2M+ parcels to ~50 calls/week. Two problems with the status quo:

1. **The score has no signal for things the co-founder cares about** — carrier count, lease expiry, vendor concentration, rent vs. comparable. These have no data today; they arrive in Slices 2 (carriers, A) and 4 (leases, D).
2. **Weights are dev-controlled.** If the co-founder learns "expiring leases with 4+ carriers are 80% of closes," he has to ask the dev to change `score.py` and re-run the whole pipeline.

## Decision

Scoring becomes **tunable and transparent** in the map app (Slice 3):

- **Score moves from baked-into-parquet to computed-on-demand client-side.** Parquet stores *components* (boolean / int fields); DuckDB-WASM computes `weights × components → score` live in the browser when weights change.
- **Co-founder dials weights live** via UI sliders. Ranking re-orders, map fades update, top-50 list reshuffles.
- **Saved scoring profiles** — named weight presets (*"my Tuesday distress-first profile"*, *"my carrier-and-expiry profile"*). Pre-Slice-4 in localStorage; Slice 4 migrates to backend tied to user account.
- **Components breakdown visible per parcel** in the lead-detail panel (*"scored 0.65 = 0.30 infra + 0.20 distress + 0.15 county tier"*).
- **Today's hardcoded weights become the default profile** — no migration pain.
- **After Slice 4** (lease docs + carriers + vendor), new signals plug into the same tunable framework: `months_to_expiry`, `rent_vs_comp`, `carrier_count`, `has_lease_on_file`, `vendor` (known-bad-actor weight). No scoring redesign then.
- **Cluster-score rollup function** (ADR-056) is itself tunable in the same UI — `max(parcel_scores) + α · log(parcel_count)` with α at 0.1 default.

## Consequences

- Map app v2 already has DuckDB-WASM + the components column; the UI work is sliders + live recompute + profile persistence. Estimated 1–2 weeks in Slice 3.
- No backend dependency for tunable scoring itself — fully client-side. Slice 3 can ship before Slice 4 (D+E) stands up the backend; profile persistence ports to backend in Slice 4.
- The dev's role becomes: expose new signals as columns + set reasonable defaults. The co-founder owns weight tuning.

## Alternatives considered

- **Status quo (hardcoded, opaque):** co-founder dependent on dev for every weight tweak. Rejected.
- **Transparent but not tunable** (show components breakdown only): half-measure; co-founder still can't experiment. Rejected.
