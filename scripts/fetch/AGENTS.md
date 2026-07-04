# Headless puller library (data acquisition)

The headless engine that fetches raw source data + tracks versions. Owns the
`DataSource` contract, the registry, the manifest, and per-source fetchers under
`sources/`. Does NOT own any UI — the data TUI lives in `../data_tui/`.

**Deep dives:** CLAUDE.md §5 (adding a source) + §6 (fragile sources);
[`docs/DATA_SOURCES.md`](../../docs/DATA_SOURCES.md), [`docs/PULLER_UX.md`](../../docs/PULLER_UX.md).

## Entry points
- `base.py` — `DataSource` base + mixins (`ManualOnlySource`), `AutomationPolicy`.
- `registry.py` — every source is appended here.
- `sources/<name>.py` — one source each, exported as `SOURCE` (or `SOURCES`).
- `sources/_helpers.py` — `version_from_head`, `head_size_ok`, `safe_extract_zip`, `fetch_zip_extracted`.
- `sources/_arcgis.py` — `ArcGisHubSource` base (edit-date probe + query-all fetch + FeatureCollection validate); HUD sources are pure configuration of it.
- `manifest.py`, `storage.py`, `http.py` — manifest, atomic storage, HTTP.

## Contracts & invariants
- **Headless: no UI imports (Textual or otherwise) anywhere in this package.**
  UI lives only in `scripts/data_tui/`. This boundary is load-bearing — keep it clean.
- **Default `AutomationPolicy` to `MANUAL_ONLY` if unsure. Never add scraping to a
  MANUAL_ONLY source without confirming the publisher's terms changed.** This is a
  legal boundary, not a convenience one.
- **Atomic writes:** download to `.partial`, rename into `current/`. Manifest
  writes go through `Manifest.save()` (temp + rename).
- `remote_version()` must be **cheap** (one HEAD / one small JSON GET) — slow probes
  block the parallel "Check for updates" sweep. Use `_helpers.version_from_head`.
- `fetch()` must call the `progress` callback while streaming (drives the UI bar).
- Use `safe_extract_zip` for all zip extraction (path-traversal protection).
- `validate()` must tolerate zip-vs-unzipped variants.

## Patterns
Adding a source: subclass `DataSource` in `sources/`, set policy + cadence,
implement `manual_walkthrough()` for MANUAL_ONLY, append to `registry.py`, document
in `docs/DATA_SOURCES.md`, add a fixture + `tests/test_<source>.py`. Full checklist: CLAUDE.md §5.

## Related context
- The TUI that drives this: [`../data_tui/AGENTS.md`](../data_tui/AGENTS.md)
- What consumes the raw output: [`../preprocess/AGENTS.md`](../preprocess/AGENTS.md)
