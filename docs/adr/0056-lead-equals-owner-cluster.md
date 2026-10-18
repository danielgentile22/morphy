# ADR-056: Lead = owner cluster as the triage unit

**Status:** Accepted. Realized by the lead-centric triage redesign ([ADR-061](0061-lead-centric-triage-redesign.md)), which built the `lead` table, the manual merge/split overrides and the `display_cluster_id` resolution. The libpostal or `usaddress` address standardization described below was never added.
**Date:** 2026-05-25
**Pairs with:** ADR-053, ADR-058. **Drives a follow-up to:** ADR-024.

## Context

The canonical schema is parcel-centric. `parcel` is the central entity, `has_tower / has_billboard / has_solar` are parcel attributes, and `owner_cluster_id` groups parcels by canonicalized owner. The demo cut treated parcels as the atomic unit.

The product phase (ADR-053) needs a workflow unit: the analyst's *unit of triage*. Outreach targets the **landowner**, not the parcel. If one LLC owns 3 parcels and 2 of them host towers, that is **one lead** (contact the LLC once), not two duplicate leads that waste a call and look careless.

Asset-side data is more granular. Each parcel hosts zero or more assets, each tower hosts zero or more carriers, and each (tower × carrier) pair has one lease. The entity stack:

```
Landowner (owner_cluster) → Parcel(s) → Asset(s) → Carrier(s) → Lease(s)
```

## Decision

**The triage unit is `owner_cluster_id`.** Each row in the triage list is one owner cluster.

Layout:

- **List view:** one row per `owner_cluster_id`. The score is a rollup of the constituent parcel scores.
- **Click → detail panel:** shows the cluster's parcels, the assets per parcel, the carriers per asset, and the leases per (asset × carrier).
- **Outreach state** (lead status, contact attempts, notes) lives on the cluster: `lead(tenant_id, owner_cluster_id, …)`.
- **Lease state** (document, extracted terms) lives on `(parcel_id, tower_asr_id, carrier_callsign)`: `lease(…)`.

**Cluster-score rollup:** `max(parcel_scores) + 0.1 · log(parcel_count)`. The best parcel anchors the score, with a modest bonus for portfolio size. It is tunable along with the rest of the scoring profile (ADR-058).

**Owner clustering algorithm (ADR-024 follow-up).** ADR-024's SHA1 of normalized name plus normalized address was good enough for a demo. For product use, a false merge means contacting the wrong person, which is worse than a false split (a duplicate contact). The upgrade:

1. Layered conservative normalization: suffix stripping (LLC/INC/CORP/JR/SR/II/III), personal-name token sort, trust and estate normalization (`X FAMILY TRUST ≡ X FAMILY LIVING TRUST → X FAMILY`), and USPS-style address standardization. **Phonetic name matching is explicitly excluded.** It is too aggressive and biases toward false merges.
2. A manual merge/split UI in the lead-detail panel. Overrides live in `owner_cluster_override(tenant_id, source_cluster_id, target_cluster_id)`. Raw cluster IDs stay in the parquet, so composites do not regenerate per manual merge. The backend computes `display_cluster_id = coalesce(override_target, raw_cluster_id)`, which survives recomputes.

## Consequences

- The `lead` table is keyed on `(tenant_id, owner_cluster_id)`, not `parcel_id`.
- Scoring (ADR-058) computes per-parcel components, then rolls up to the cluster. The rollup function is tunable in the same UI.
- This ADR is the follow-up to ADR-024. The original SHA1 stays for the analytical pipeline (no schema break). The normalization upgrades run *before* the SHA1 hashing.
- libpostal was preferred for address normalization (quality), with pure-Python `usaddress` as the fallback if libpostal caused dependency pain.

## Alternatives considered

- **Parcel as lead** (status quo). Duplicate leads mean duplicate calls. Rejected.
- **Asset as lead** (one per tower × carrier). Fragments outreach state: the same landowner appears N times. Rejected.
- **Phonetic name matching for better recall.** Rejected. It biases toward false merges, which are the costlier error when each lead is a direct contact.
