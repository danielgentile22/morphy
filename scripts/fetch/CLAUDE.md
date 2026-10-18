# Headless puller library (data acquisition)

The headless engine that fetches raw source data + tracks versions. Owns the
`DataSource` contract, the registry, the manifest, and per-source fetchers under
`sources/`. Does NOT own any UI; the data TUI lives in `../data_tui/`.

**Deep dives:** [`docs/DATA_SOURCES.md`](../../docs/DATA_SOURCES.md), [`docs/PULLER_UX.md`](../../docs/PULLER_UX.md),
[`docs/LIMITATIONS.md`](../../docs/LIMITATIONS.md) (per-source upstream-failure tracking).

## Entry points
- `base.py`: `DataSource` base + mixins (`ManualOnlySource`), `AutomationPolicy`.
- `registry.py`: every source is appended here.
- `sources/<name>.py`: one source each, exported as `SOURCE` (or `SOURCES`).
- `sources/_helpers.py`: `version_from_head`, `head_size_ok`, `safe_extract_zip`, `fetch_zip_extracted`.
- `sources/_arcgis.py`: `ArcGisHubSource` base (edit-date probe + query-all fetch + FeatureCollection validate). The Department of Housing and Urban Development (HUD) sources are pure configuration of it.
- `manifest.py`, `storage.py`, `http.py`: manifest, atomic storage, HTTP.

## Contracts & invariants
- **Headless: no UI imports (Textual or otherwise) anywhere in this package.**
  UI lives only in `scripts/data_tui/`. This boundary is load-bearing; keep it clean.
- **Default `AutomationPolicy` to `MANUAL_ONLY` if unsure. Never add scraping to a
  MANUAL_ONLY source without confirming the publisher's terms changed.** This is a
  legal boundary, not a convenience one.
- **Atomic writes:** download to `.partial`, rename into `current/`. Manifest
  writes go through `Manifest.save()` (temp + rename).
- `remote_version()` must be **cheap** (one HEAD / one small JSON GET). Slow probes
  block the parallel "Check for updates" sweep. Use `_helpers.version_from_head`.
- `fetch()` must call the `progress` callback while streaming (drives the UI bar).
- Use `safe_extract_zip` for all zip extraction (path-traversal protection).
- `validate()` must tolerate zip-vs-unzipped variants.

## Adding a new data source

1. Create `sources/<your_source>.py` with one `DataSource` subclass exported as
   `SOURCE` (or `SOURCES = [...]`). Prefer a mixin from `base.py` when one fits:
   `ManualOnlySource` supplies `remote_version() → "manual"` + `fetch() → RuntimeError`.
2. Set `AutomationPolicy`; default to `MANUAL_ONLY` if unsure.
3. Set `update_cadence_days` ([`docs/DATA_FRESHNESS.md`](../../docs/DATA_FRESHNESS.md) §2).
4. For MANUAL_ONLY: implement `manual_walkthrough()` returning ordered steps with
   deep links + expected files ([`docs/PULLER_UX.md`](../../docs/PULLER_UX.md) §4).
5. Append to `registry.py`.
6. Document in [`docs/DATA_SOURCES.md`](../../docs/DATA_SOURCES.md).
7. If a normalizer is needed: `../preprocess/normalizers/<source>.py`,
   `@register_normalizer`, declare `canonical_types`, add to `../preprocess/registry.py`.
8. Add `tests/fixtures/<source>_raw/` + `tests/test_<source>.py`
   ([`docs/TESTING.md`](../../docs/TESTING.md) §9).

## Known fragile upstreams

- FCC Antenna Structure Registration (ASR) and Universal Licensing System (ULS)
  bulk URLs: the publisher restructures them.
- Federal Aviation Administration Digital Obstacle File (FAA DOF) archive page:
  path renames.
- HUD ArcGIS layers: service rename or layer-ID change (`remote_version()` probes
  them).
- USDA Economic Research Service (ERS) file URL: migrates between editions.
- Lawrence Berkeley National Laboratory Tracking the Sun (LBNL TTS) annual
  filename: the scraper finds the newest.
- Energy Information Administration (EIA) 860 / 860M placeholder pages: caught
  by the `min_bytes` check.

## Related context
- The TUI that drives this: [`../data_tui/CLAUDE.md`](../data_tui/CLAUDE.md)
- What consumes the raw output: [`../preprocess/CLAUDE.md`](../preprocess/CLAUDE.md)
