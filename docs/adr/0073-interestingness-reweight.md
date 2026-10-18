# ADR-073: Reweight interestingness toward small-portfolio, low-value, high-carrier towers

**Status:** Accepted and implemented. The default preset is the thesis below (`smallPortfolio` / `lowValue` / `carriers` features, distress demoted). There is a new owner-level `carrier_count` (owners-index v8), and the baked score's portfolio log-bonus is clamped.
**Date:** 2026-07-03
**Origin:** one of seven decisions (ADR-070-076) from a data audit, whose working files are not part of this repo.
**Amends:** [ADR-058](0058-tunable-transparent-scoring.md). The **default weights and owner rollup** change; the tunable, transparent client-side framework stands unchanged.
**Prerequisite (landed):** the score-factor bars were made honest first, so weights can move without the display lying.

## Context

The audit found the default score is dominated by the coarse **county-distress tier (~40% of mass)** while the tower itself contributes **~0.5%**. The owner-level rollup is **portfolio-dominated and unclamped**, so a tower company with thousands of towers floats to the top by breadth alone. The user's actual thesis: chase owners with **few** towers (avoid the giants), **lower** assessed value, and **more** carriers on the tower.

## Decision

A new **default preset** (everything still tunable per ADR-058):

- **Portfolio size → inverted and clamped.** Fewer towers per owner ranks higher; a hard clamp floors giant portfolios so breadth can't dominate. This replaces the unclamped rollup bias.
- **Value → inverse term.** Lower value ranks higher. It uses the **owner-level market** rollup (`total_assessed_value`). Per the ADR-070 (2026-07-03) amendment, the owner-level axis stays on market because statutory is null for MT and mixes state fractions across states. Statutory stays a per-parcel display figure.
- **Carrier count → linear reward.** More carriers on the tower ranks higher.
- **County distress → demoted** from ~40% to a minor tiebreaker.
- The owner rollup stays an aggregate of the owner's tower scores (ADR-058 amendment), but the aggregate is **clamped** so portfolio breadth doesn't substitute for per-tower interest.

## Consequences

- Top-N owner and parcel ordering changes materially. **Spot-check old vs new and get a human sanity review before commit.**
- Score bars remain truthful under the new weights.
- These are **defaults**; the user still dials weights live.
- Likely client-side only (weights plus clamp), but **verify whether the clamp needs a new component column** in the parquet. If so, composite regen.

## Alternatives considered

- **Keep the distress-weighted default.** Rejected. It doesn't match the user's thesis.
- **Unclamped inversion.** Rejected. A single huge owner holding one cheap tower would top the list spuriously.
