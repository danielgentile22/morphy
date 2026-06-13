# Desktop puller (PySide6 UI)

The PySide6 desktop app that drives the headless puller — "Check for updates",
manual-download walkthroughs, fetch progress, and preprocess triggering. Owns all
Qt/UI concerns. Does NOT own fetch logic or source definitions — those live
headless in `../scripts/fetch/` and this layer only calls into them.

**Deep dive:** [`docs/PULLER_UX.md`](../docs/PULLER_UX.md).

## ⛔ Freeze policy (PRD #138)

**This subsystem is frozen.** It keeps working and keeps being used, but receives
**no new features and no investment beyond keep-the-lights-on bug fixes.** It is
~2,900 lines of untested Qt pinned to an old PySide6 (newer releases broke on macOS),
carrying ~700 MB of dependency, all for an audience of one — every feature added
deepens that fragile, untestable investment.

- **Bug-fix-only.** Keep-the-lights-on fixes stay allowed (so a small breakage never
  forces a rushed rewrite). New features do not — **route every puller feature request
  to the Textual TUI successor scope in
  [PRD #138](https://github.com/danielgentile22/infra-lease-analytics/issues/138), or
  defer it.** Do not add to the Qt surface by default.
- **Named triggers** — building the successor activates when *any one* fires:
  1. a puller feature the team actually needs;
  2. the PySide6 pin breaks on a platform the operator uses;
  3. the dependency blocks other work (e.g. a toolchain or Python-version move).
- **Successor:** a **Textual TUI** that is a thin UI over the *unchanged* headless
  `../scripts/fetch/` + `../scripts/preprocess/` libraries (no logic moves into the UI),
  CI-testable via Textual's pilot/snapshot tests, preserving the manual-walkthrough
  flow. The full successor spec — source table with freshness badges, parallel
  check-for-updates sweep, sequential pulls with progress, manual-walkthrough +
  file-picker install, preprocess runner, diagnose — lives in PRD #138; the
  trigger-day build starts from there, not a fresh debate.
- **Retirement:** once the successor covers that scope and has tests, the Qt app and
  the PySide6 pin are deleted in the same change.

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
