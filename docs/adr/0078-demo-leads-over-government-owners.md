# ADR-078: Demo leads sit on government owners only

**Status:** Accepted. Implemented in the public demo deployment (`morphy-demo`).
**Date:** 2026-10-20
**Amends:** [ADR-077](0077-read-only-demo-credential.md) (decision 5, seeding).

## Context

ADR-077 seeded the demo board's six fictional storylines over the top-scoring business-entity owners in the owners index. Those are real companies from public parcel records, and some are small: a family farm company showed as "Contacted", another as "Uninterested". The notes say every entry is fictional, but a status badge next to a real company's name reads as a claim that the contact happened. The seed's allow-list also named `corporate`, a kind the owner classifier never emits ([ADR-076](0076-owner-type-classifier.md) uses `corporation`), so in practice only LLCs were seeded.

Invented owner names are not an option: a lead is an owner cluster ([ADR-056](0056-lead-equals-owner-cluster.md)), and the lead page reads the name, parcels and towers from the owners index.

## Decision

`python -m app.demo_seed` picks only owners the classifier tags `gov` (federal agencies, states, counties, cities, public authorities) that hold at least one tower, highest score first. A fictional triage story about a public agency harms no private party, and the demo index has hundreds of tower-holding government owners to draw from. Everything else in ADR-077 decision 5 stands.

## Consequences

- The live demo's board must be reseeded. The seed leaves a board that already has leads alone, so the existing demo leads are cleared first on the machine.
- The board shows public owners such as the USDA Forest Service and the State of Montana instead of private companies. The board looks less like a real pipeline, which is the point.
