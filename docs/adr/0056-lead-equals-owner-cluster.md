# ADR-056: Lead = owner-cluster as the triage primitive

**Status:** Accepted — **locked design, UNIMPLEMENTED as of 2026-05-29 (Slice 4; no `backend/` code exists yet).**
**Date:** 2026-05-25
**Pairs with:** ADR-053, ADR-058. **Drives a follow-up to:** ADR-024.

## Context

Today's canonical schema is parcel-centric: `parcel` is the central entity, `has_tower / has_billboard / has_solar` are parcel attributes, `owner_cluster_id` groups parcels by canonicalized owner. The pitch cut treated parcels as the atomic unit.

The product phase (ADR-053) introduces a workflow primitive — the co-founder's *unit of triage*. He pitches the **landowner**, not the parcel. If one LLC owns 3 parcels and 2 host towers, that's **one lead** (call the LLC once), not two duplicate leads (= wasted call + looks unprofessional).

Asset-side data is more granular: each parcel hosts 0+ assets; each tower hosts 0+ carriers; each (tower × carrier) has 1 lease. Entity stack:

```
Landowner (owner_cluster) → Parcel(s) → Asset(s) → Carrier(s) → Lease(s)
```

## Decision

**Triage primitive = `owner_cluster_id`.** Each row in the triage list is one owner-cluster.

Layout:

- **List view:** one row per `owner_cluster_id`. Score = rollup of constituent parcel scores.
- **Click → detail panel:** shows cluster's parcels, assets per parcel, carriers per asset, leases per (asset × carrier).
- **Outreach state** (lead status, contact attempts, notes) lives on the cluster — `lead(tenant_id, owner_cluster_id, …)`.
- **Lease state** (document, extracted terms) lives on `(parcel_id, tower_asr_id, carrier_callsign)` — `lease(…)`.

**Cluster-score rollup function:** `max(parcel_scores) + 0.1 · log(parcel_count)`. Best-parcel-anchored with a modest portfolio-size bonus. Tunable along with the rest of the scoring profile (ADR-058).

**Owner clustering algorithm (ADR-024 follow-up)** — ADR-024's SHA1(normalized name + normalized address) is "good-enough for pitch" but for product use, false merges = wrong-person calls (worse than false splits = duplicate calls). Slice 4 strengthens:

1. Layered conservative normalization: suffix stripping (LLC/INC/CORP/JR/SR/II/III), personal-name token sort, trust/estate normalization (`X FAMILY TRUST ≡ X FAMILY LIVING TRUST → X FAMILY`), USPS-style address standardization. **Phonetic name match explicitly excluded** — too aggressive, biases toward false merges.
2. Manual merge/split UI in the lead-detail panel. Overrides in `owner_cluster_override(tenant_id, source_cluster_id, target_cluster_id)`. Raw cluster IDs stay in the parquet (composites don't regenerate per manual merge); backend computes `display_cluster_id = coalesce(override_target, raw_cluster_id)`. Survives recomputes.

## Consequences

- Slice 4's `lead` table keyed on `(tenant_id, owner_cluster_id)` not parcel_id.
- Scoring (ADR-058) computes per-parcel components then rolls up to cluster; rollup function is itself tunable in the same UI.
- ADR-024 effectively gets a follow-up via this ADR. Original SHA1 stays for the analytical pipeline (no schema break); the normalization upgrades layer in *before* the SHA1 hashing.
- libpostal preferred for address normalization (quality); fall back to pure-Python `usaddress` if Slice 4 build hits dep-management pain.

## Alternatives considered

- **Parcel-as-lead** (status quo): duplicate leads = duplicate calls = unprofessional. Rejected.
- **Asset-as-lead** (one per tower × carrier): fragments outreach state — same landowner appears N times. Rejected.
- **Phonetic name match for stronger recall:** rejected; bias toward false merges, worse for cold-call business.
