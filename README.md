# pilot

Feasibility prototype for **cell-tower ground-lease renegotiation
analytics**. Joins tower locations to parcel records to economic-distress
overlays, using only free public data. Currently focused on a 3–5 state
pitch-quality cut.

> Read [docs/SCOPE.md](docs/SCOPE.md) first if you want to know what we're
> building right now. Read [PROJECT_BRIEF.md](PROJECT_BRIEF.md) for the
> business case.

---

## Three subsystems

| Subsystem | Path | Purpose |
|---|---|---|
| **Data Puller** | `app_puller/` | PySide6 desktop UI; fetches raw data into `data/raw/<source_id>/current/`. |
| **Preprocess pipeline** | `scripts/preprocess/` | Registry-driven Normalizer + Join + View framework; per-state Composer. |
| **Map app** | `app/` | Leaflet static SPA reading per-state `catalog.json`. (v2 rebuild deferred — see [docs/MAP_APP_REHAUL.md](docs/MAP_APP_REHAUL.md).) |

[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) has the full system diagram
+ data flow.

---

## Quick start

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 1. Pull raw data

```bash
python -m app_puller
```

In the puller: **Check for updates** → **Pull all missing**. For
MANUAL_ONLY sources, click **Walk me through** on each row.
[docs/PULLER_UX.md](docs/PULLER_UX.md) is the design spec.

### 2. Preprocess

```bash
python scripts/preprocess.py                    # all sources + all states
python scripts/preprocess.py --state 05         # just Arkansas
python scripts/preprocess.py --source ar_parcels --force-rebuild
python scripts/preprocess.py --rebuild-manifest # resync manifest with disk
python scripts/preprocess.py --list-views       # discoverability
```

Outputs:

- `data/processed/normalized/<source>/` — canonical-schema Parquet +
  GeoJSON + `raw.parquet` + `quality_report.json`.
- `data/processed/composite/<state_fips>/` — joined per-state outputs +
  views + `catalog.json` + `summary.json`.

### 3. View the map

```bash
python -m http.server 8765     # from repo root
# Open http://localhost:8765/app/  (optionally  ?state=05  to deep-link)
```

The state selector auto-populates from `data/processed/composite/*/catalog.json`.

### 4. Tests *(after Section 6 of the production-readiness plan lands)*

```bash
pytest
ruff check . && ruff format --check .
```

---

## Where to look

**Front door** (start here):

- [docs/SCOPE.md](docs/SCOPE.md) — what's in / out of the current cut
- [docs/STATUS.md](docs/STATUS.md) — what works today
- [docs/GOALS.md](docs/GOALS.md) — success criteria

**Deep dives:**

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — how the system fits together
- [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md) — per-source schema + license + automation policy
- [docs/DATA_FRESHNESS.md](docs/DATA_FRESHNESS.md) — when each source needs a refresh
- [docs/LIMITATIONS.md](docs/LIMITATIONS.md) — caveats and pre-commercial blockers
- [docs/SECURITY.md](docs/SECURITY.md) — PII / data-handling posture
- [docs/GLOSSARY.md](docs/GLOSSARY.md) — domain-term reference

**Where we're going:**

- [docs/ROADMAP.md](docs/ROADMAP.md) — past / present / future
- [docs/DECISIONS.md](docs/DECISIONS.md) — locked-in design choices
- [docs/MAP_APP_REHAUL.md](docs/MAP_APP_REHAUL.md) — full map app v2 plan (DEFERRED)
- [docs/CHANGELOG.md](docs/CHANGELOG.md) — version history

**Working with AI coding agents:**

- [CLAUDE.md](CLAUDE.md) — orientation for Claude Code sessions

---

## Anchor states for v1

| State | FIPS | Status |
|---|---|---|
| Arkansas | 05 | ✅ Working end-to-end |
| North Carolina | 37 | 🟡 Refresh needed |
| Montana | 30 | 🟡 Pull required |
| Utah | 49 | 🟡 Pull required |
| Florida | 12 | 🟡 Stretch (via per-county FDOR NAL) |

See [docs/SCOPE.md §2](docs/SCOPE.md) for why these.

---

## Repository layout

```
pilot/
├── README.md                 (you are here)
├── CLAUDE.md                 AI-agent orientation
├── PROJECT_BRIEF.md          Business case
├── requirements.txt
├── app/                      Leaflet map (v1)
├── app_puller/               PySide6 desktop puller
├── scripts/
│   ├── preprocess.py         CLI wrapper
│   ├── preprocess/           Normalizer/Join/View framework
│   ├── fetch/                Headless puller library
│   ├── verify_raw.py         File-signature contents check
│   └── diagnose.py           LLM-powered verify diagnosis
├── data/                     (git-ignored; ~15 GB raw)
│   ├── raw/<source>/current/
│   └── processed/{normalized,composite}/
├── docs/                     All deep-dive documentation
│   ├── archive/              Historical docs (preprocess v1, etc.)
│   └── pitch-assets/         Screenshots / GIFs for pitch deck
└── tests/                    (added in Section 6 of work plan)
```

---

## License + status

This is a **feasibility prototype**, not a released product. Outputs
contain parcel-owner names + mailing addresses (PII when combined) —
treat per [docs/SECURITY.md](docs/SECURITY.md). The repo itself is
private until access controls land.

Active work plan lives at
`.claude/plans/cached-wobbling-token.md` (in-flight production-
readiness push). Doc work is the current phase.
