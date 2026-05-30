# PROTOTYPE — lead-centric triage redesign

**Throwaway.** Answers a design question for [ADR-061](../docs/adr/0061-lead-centric-triage-redesign.md). Delete this whole `prototype/` folder once the question is answered and the winner is folded into the real `app/`.

## The question this answers

> Where should the (redefined, lead-centric) **filters** live — a slim **top bar + "More" popover**, or a decluttered **collapsible left drawer**? And does the whole reframed flow (structures-first map → Candidates → My-Leads kanban → cross-state Lead page) feel right before we build it for real on the backend?

The `?variant=` switcher flips **only the filter placement** — everything else is held constant on purpose, so the comparison is apples-to-apples.

- `variant=topbar` → **A — Top filter bar** (quick filters: State / Distress / Structure / Score, plus "⊕ More filters")
- `variant=drawer` → **B — Left drawer** (Score on top; Location / Distress / Owner / Structure groups; Advanced collapsed)

## How to run

ES-module imports need to be served over HTTP (not `file://`). Use the repo's existing static server:

```bash
# from the repo root
source .venv/bin/activate
python scripts/serve.py 8765
# then open:
#   http://localhost:8765/prototype/?variant=topbar
#   http://localhost:8765/prototype/?variant=drawer
```

Flip variants with the floating bottom bar or the **← / →** keys. Surfaces: top-nav **Map · Candidates · My Leads**; click any tower (map), row (Candidates), or card (kanban) to open a **Lead** page. Drag kanban cards between lanes to change status. All edits are in-memory (no persistence — that's deliberate).

## What's mocked / faked

- ~24 cross-state landowner Leads (`mock.js`), towers scattered around the 4 anchor-state centroids.
- No backend, no auth, no real parcels/PMTiles/DuckDB. Distress, scores, contacts are invented.
- The map is real MapLibre (Carto Positron basemap, clustered tower points) so density feels right.

## VERDICT (2026-05-30)

- **Filter placement chosen: A — slim top filter bar + "More" popover.** Drawer (Variant B) is dropped.
- Flow otherwise confirmed (structures-first map → Candidates → My-Leads kanban → cross-state Lead page).
- Next: fold the top-bar layout into the real `app/`, drop the drawer variant + the `?variant=` switcher, then delete `prototype/`.
