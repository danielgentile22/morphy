# DEPLOYMENT — How this runs

**Last updated:** 2026-05-19
**Status:** Local-only for v1 pitch. No cloud / hosted deployment.

This doc describes how to stand up the project locally — what to install,
how to run each subsystem, and how to ship outputs to a partner without
hosting anything.

---

## 1. Where this runs today

All four surfaces run locally on a developer's machine:

| Surface | Run command | Port / location |
|---|---|---|
| **Puller** | `python -m app_puller` | Desktop window |
| **Preprocess CLI** | `python scripts/preprocess.py [flags]` | Terminal |
| **Map app** | `python -m http.server 8765` then open `http://localhost:8765/app/` | localhost:8765 |
| **Tests** | `pytest` (after Section 6 lands) | Terminal |

There is **no production / hosted instance.** Hosted deployment is a
post-pitch concern (see [ROADMAP.md](./ROADMAP.md) → "Hosted deployment").

---

## 2. Prerequisites

| Component | Version | Why |
|---|---|---|
| Python | 3.11 | Tested baseline; pyogrio + PySide6 known good |
| macOS arm64 / Linux x86_64 | Any recent | macOS arm64 is the primary dev environment |
| Homebrew (macOS) | — | For optional `gh` CLI, future `tippecanoe` in map app v2 |
| Disk space | ≥ 50 GB free | Raw data + composites; AR alone is ~3 GB raw, ~5 GB normalized |
| RAM | ≥ 16 GB recommended | Preprocess on AR (2.1M rows) peaks at ~6 GB RSS |

After map app v2 lands (deferred):

| Component | Version | Why |
|---|---|---|
| Node.js | ≥ 20 | Vite + Svelte build for map app v2 |
| Tippecanoe | ≥ 2.45 | PMTiles vector tile generation |

---

## 3. First-time setup

```bash
# Clone (after Section 2 of the work plan creates the GitHub repo)
git clone git@github.com:<user>/pilot.git
cd pilot

# Python environment
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Verify installation
python scripts/verify_raw.py     # No raw data yet — expect "missing" rows
python -m app_puller             # Should launch the puller window
```

The first run sets up empty `data/raw/` and `data/processed/`
directories (gitignored).

---

## 4. Standard workflow

### 4.1 Refresh data

1. Launch the puller: `python -m app_puller`.
2. Click **Check for updates** (parallel HEAD across all sources).
3. The puller's "What needs my attention" panel surfaces:
   - Auto sources past their `next_recommended_check_at` → click
     **Pull all stale** to refresh.
   - Manual sources stale → walkthrough modal guides each download.
4. Click **Rescan disk** after any manual download.
5. Click **Verify contents** to confirm each source has expected files.

### 4.2 Preprocess

Either via the puller:

- Click **Preprocess** → state dropdown (or "all") → click **Run**.

Or via CLI:

```bash
python scripts/preprocess.py                   # everything
python scripts/preprocess.py --state 05        # one state
python scripts/preprocess.py --source ar_parcels --force-rebuild
python scripts/preprocess.py --rebuild-manifest  # sync manifest from disk
```

Outputs land at `data/processed/normalized/<source>/` and
`data/processed/composite/<state_fips>/`.

### 4.3 View the map

```bash
python -m http.server 8765
# Open http://localhost:8765/app/
# Or http://localhost:8765/app/?state=05 to deep-link a state
```

The map app auto-discovers composed states via `catalog.json` probes.

### 4.4 Run tests (after Section 6)

```bash
pytest                                     # full suite
pytest --cov=scripts.preprocess            # with coverage
ruff check . && ruff format --check .      # lint + format
```

---

## 5. Sharing outputs (no hosted instance)

Until hosted deployment lands, sharing the system with a partner /
investor means:

### 5.1 Best: walk them through live (screen share)

- Run the map app locally; share screen.
- Pitch scenarios in [SCOPE.md §5](./SCOPE.md) walk cleanly.

### 5.2 Static: hand them a ZIP

For asynchronous review:

```bash
# Bundle the public-facing app + per-state composites
tar -czf pilot-demo-$(date +%Y%m%d).tar.gz \
    app/ \
    data/processed/composite/05/ \
    data/processed/composite/37/ \
    docs/INVESTOR_BRIEF.md \
    docs/NUMBERS.md \
    docs/SCOPE.md \
    README.md
```

The recipient unpacks, runs `python -m http.server 8765`, opens
localhost:8765/app/. Works without our env. **PII caveat:** this
tarball contains parcel-owner names + mailing addresses. Encrypt at
rest; share via secure channel.

### 5.3 Pitch-deck assets

`docs/pitch-assets/*.png` / `*.gif` are the demo screenshots.
Reference these in the pitch deck. They live in the repo so a
co-founder onboarding the deck has the source files.

---

## 6. Environment variables

Most runs need no env vars. Optional:

| Variable | Used by | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | `scripts/diagnose.py` (puller "Diagnose this failure") | LLM-powered verify-failure diagnosis (~$0.04 per call) |
| `REGRID_S3_BUCKET`, `REGRID_S3_PREFIX`, `AWS_*` | `scripts/fetch/sources/regrid_parcels.py` | Only activates the Regrid source if all set (paid; out of scope for v1) |

Store in `.env` (git-ignored) and source before running:

```bash
source .env
python -m app_puller
```

---

## 7. Backups

Currently manual. Before any pitch:

1. `tar -czf backups/pilot-$(date +%Y%m%d-%H%M).tar.gz data/processed/`
   — composite outputs are the expensive thing; raw can always be
   re-pulled.
2. Push to a personal cloud backup (iCloud Drive, Dropbox, etc.) —
   **encrypted** because parcel data is PII.

Post-pitch: automated daily snapshot to a small object-storage
bucket; encrypted at rest.

---

## 8. Production deployment (future, not in scope)

Locked architectural decisions for when we get there
([DECISIONS.md](./DECISIONS.md) ADR-030, ADR-031, ADR-040):

- Map app v2: static-site hosted bundle (S3 + CloudFront or
  equivalent) — no backend server.
- Per-state PMTiles served via HTTP range requests.
- DuckDB-WASM queries parquet files directly from object storage.
- Access controls via Cloudflare Access or AWS IAM (single-user
  initially; multi-user later).
- Parcel data PII never publicly cached / indexed.

None of this is built. Tracked in
[MAP_APP_REHAUL.md](./MAP_APP_REHAUL.md).

---

## 9. Quick troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Puller crashes on launch | PySide6 version mismatch | `pip install --upgrade --force-reinstall PySide6==6.7.3` |
| Preprocess fails: `ImportError: openpyxl` | Missing optional dep | `pip install -r requirements.txt` (openpyxl is now required) |
| Composite written but map shows "no data" | Catalog probe missed | Ensure `python -m http.server` was started from repo root (not from `app/`) |
| Stale manifest disagrees with disk | Interrupted run | `python scripts/preprocess.py --rebuild-manifest` |
| Tests fail with "no such fixture" | New fixture not created | Run `pytest --collect-only` to see test IDs; check `tests/fixtures/` |
