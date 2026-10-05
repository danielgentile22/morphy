# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

## Before exploring, read these

- **`GLOSSARY.md`** at the repo root — domain language, glossary terms, mental model.
- **`docs/adr/`** — read ADRs that touch the area you're about to work in.
- **Legacy decisions** still live inlined in **`docs/DECISIONS.md`** (e.g. ADR-001…ADR-051). Treat both as authoritative until the inline ADRs are migrated into `docs/adr/`. When in doubt, the newer file wins.
- Companion domain references: **`PROJECT_BRIEF.md`**, **`docs/SCOPE.md`**, **`docs/GLOSSARY.md`**.

If `GLOSSARY.md` or `docs/adr/` is empty, **proceed silently**. Don't flag absence; don't suggest creating files upfront. The producer skill (`/grill-with-docs`) creates them lazily when terms or decisions actually get resolved.

## File structure

Single-context repo:

```
/
├── GLOSSARY.md
├── PROJECT_BRIEF.md
├── docs/
│   ├── adr/                       ← new ADRs go here
│   ├── DECISIONS.md               ← legacy inline ADRs (ADR-001..051)
│   ├── GLOSSARY.md
│   └── SCOPE.md
```

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined in `GLOSSARY.md` / `docs/GLOSSARY.md`. Don't drift to synonyms the glossary explicitly avoids.

If the concept you need isn't in the glossary yet, that's a signal — either you're inventing language the project doesn't use (reconsider) or there's a real gap (note it for `/grill-with-docs`).

## Flag ADR conflicts

If your output contradicts an existing ADR (in either `docs/adr/` or the legacy `docs/DECISIONS.md`), surface it explicitly rather than silently overriding:

> _Contradicts ADR-041 (no LLC unmasking) — but worth reopening because…_
