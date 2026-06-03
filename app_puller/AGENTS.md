# Desktop puller (PySide6 UI)

The PySide6 desktop app that drives the headless puller — "Check for updates",
manual-download walkthroughs, fetch progress, and preprocess triggering. Owns all
Qt/UI concerns. Does NOT own fetch logic or source definitions — those live
headless in `../scripts/fetch/` and this layer only calls into them.

**Deep dive:** [`docs/PULLER_UX.md`](../docs/PULLER_UX.md).

## Entry points
- `__main__.py` — `python -m app_puller`.
- `main_window.py` — the main window + wiring.
- `workers.py` — background threads (fetch/check run off the UI thread).
- `walkthrough_dialog.py`, `manual_install.py` — MANUAL_ONLY click-through flows.
- `preprocess_dialog.py` — preprocess trigger UI.

## Contracts & invariants
- **Qt lives only here.** This is the single boundary that keeps `scripts/fetch/`
  importable headless — never let Qt leak downward, and keep this layer a thin shell
  over the fetch library rather than reimplementing source/fetch logic.
- Long-running work (fetch, version checks) runs on `workers.py` threads, never on
  the UI thread.
- Source behavior (cadence, policy, walkthrough steps) comes from the `DataSource`
  definitions in `scripts/fetch/sources/` — render it, don't hardcode it here.

## Run
`source .venv/bin/activate && python -m app_puller`

## Related context
- The headless library this drives: [`../scripts/fetch/AGENTS.md`](../scripts/fetch/AGENTS.md)
