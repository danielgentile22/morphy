# CONTEXT

Domain language and mental model for this repo. Read this before exploring the codebase.

This file is intentionally a stub — the `/grill-with-docs` skill fills it in lazily as domain terms get resolved during real conversations. Until then, the canonical sources of domain language are:

- [PROJECT_BRIEF.md](PROJECT_BRIEF.md) — what the business does and the data problem it solves
- [docs/SCOPE.md](docs/SCOPE.md) — what's in/out right now (anchor states, source list)
- [docs/GLOSSARY.md](docs/GLOSSARY.md) — defined terms
- [docs/DECISIONS.md](docs/DECISIONS.md) — locked design choices (legacy ADRs ADR-001..051; new ADRs go in `docs/adr/`)

## Core concepts (one-line)

- **Asset** — a piece of infrastructure on someone's land (initially: a cell tower from FCC ASR).
- **Landowner** — the party who owns the parcel under an asset; identified by joining ASR coordinates → state parcel data.
- **Ground lease** — the contract between landowner and infrastructure operator; the business helps landowners renegotiate these.
- **Distress overlay** — HUD OZ/QCT, USDA distress, ARC distress; used to prioritize outreach to landowners likely to renegotiate.
- **Anchor states** — the pilot's geographic cut: AR (`05`), NC (`37`), MT (`30`), and FL (`12`) as a stretch.
- **Normalizer / Join / View** — the three-stage preprocess framework (see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)).

Expand this file when a real conversation surfaces a term that wasn't obvious.
