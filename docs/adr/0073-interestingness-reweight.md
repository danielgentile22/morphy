# ADR-073: Reweight interestingness toward small-portfolio, low-value, high-carrier towers

**Status:** Accepted — **implemented** (#218, approach A). Default preset = the thesis (`smallPortfolio` / `lowValue` / `carriers` features, distress demoted); new owner-level `carrier_count` (owners-index v8); the baked score's portfolio log-bonus clamped.
**Date:** 2026-07-03
**Amends:** [ADR-058](0058-tunable-transparent-scoring.md) — the **default weights + owner rollup** change; the tunable/transparent client-side framework stands unchanged.
**Prerequisite (landed):** [#214](https://github.com/danielgentile22/morphy/issues/214) — the score-factor bars are honest, so weights can move without the display lying.

## Context

The audit found the default score is dominated by the coarse **county-distress tier (~40% of mass)** while the tower itself contributes **~0.5%**; the owner-level rollup is **portfolio-dominated and unclamped**, so a towerco with thousands of towers floats to the top by breadth alone. The co-founder's actual thesis (stated this session): chase owners with **few** towers (avoid the giants), **lower** assessed value, and **more** carriers on the tower.

## Decision

A new **default preset** (everything still tunable per ADR-058):

- **Portfolio size → inverted + clamped.** Fewer towers per owner ranks higher; a hard clamp floors giant portfolios so breadth can't dominate. Replaces the unclamped rollup bias.
- **Value → inverse term.** Lower value ranks higher. Uses the **owner-level market** rollup (`total_assessed_value`) — per the ADR-070 (2026-07-03) amendment, the owner-level axis stays on market because statutory is null for MT and mixes state fractions cross-state. Statutory stays a per-parcel display figure.
- **Carrier count → linear reward.** More carriers on the tower, higher.
- **County distress → demoted** from ~40% to a minor tiebreaker.
- Owner rollup stays an aggregate of the owner's tower scores (ADR-058 amendment), but the aggregate is **clamped** so portfolio breadth doesn't substitute for per-tower interest.

## Consequences

- Top-N owner and parcel ordering changes materially — **spot-check old vs new + human sanity-review before commit**.
- Score bars remain truthful (#214) under the new weights.
- These are **defaults**; the co-founder still dials weights live.
- Likely client-side-only (weights + clamp), but **verify whether the clamp needs a new component column** in the parquet — if so, composite regen.

## Alternatives considered

- **Keep the distress-weighted default** — rejected; it doesn't match the co-founder's thesis.
- **Unclamped inversion** — rejected; a single huge owner holding one cheap tower would top the list spuriously.
