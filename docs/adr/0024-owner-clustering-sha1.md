# ADR-024: Owner clustering = SHA1(normalized name + address)

**Status:** Follow-up locked in [ADR-056](0056-lead-equals-owner-cluster.md) — Slice 4 layers stronger conservative normalization (suffix stripping, name-token sort, trust/estate normalization, USPS address standardization) + a manual merge/split UI before the SHA1 hashing. Phonetic name match explicitly excluded (biases toward false merges).
**Date:** 2026-05

## Context

Detecting "this owner owns 12 parcels" requires canonicalizing names and addresses (case, punctuation, suffixes).

## Decision

`cluster_id = sha1(normalize_owner_name(name) + '|' + normalize_address(addr))`. Implementation in `scripts/preprocess/cluster.py`.

## Consequences

Cluster IDs are stable across runs given the same inputs. Imperfect (e.g., "Smith Family Trust" vs "Smith Family Living Trust" cluster apart); good-enough for the pitch.
