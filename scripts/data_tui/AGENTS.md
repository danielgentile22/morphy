# Data TUI (the puller)

Textual terminal app covering the full data lifecycle — pull → preprocess →
verify → deploy — with zero terminal commands (PRD #233). Succeeded the Qt
desktop puller, which was deleted with its PySide6 pin in #240 (PRD #138
retirement clause). Run with `python -m data_tui`.

**Deep dives:** [`docs/PULLER_UX.md`](../../docs/PULLER_UX.md) (design spec),
PRD #233 (build spec), CLAUDE.md §5 (adding a source).

## Entry points
- `app.py` — the Textual app: sources table, check sweep, background pull /
  preprocess workers, activity log.
- `freshness.py` — pure badge + attention logic (fresh / due soon / stale /
  missing / endpoint-dead / manual / deferred).
- `planner.py` — pure refresh planner: (registry, fetch manifest, preprocess
  manifest) → which sources to pull, which states to preprocess, deploy_warranted.
- `manual.py` — walkthrough + install-from-file screens over `fetch.install`.
- `verify.py` — pure composite verify vs the last deploy receipt.
- `deploy.py` / `deploy_ui.py` — deploy.sh driver (data + smoke legs, restart
  sequencing) and the confirm-gated screen.
- `notify.py` — best-effort desktop notifications (osascript / notify-send).

## Contracts & invariants
- **Thin shell.** The headless `fetch` / `preprocess` libraries and `deploy.sh`
  stay unchanged; anything decision-shaped lives in a pure module
  (`freshness`, `planner`, `verify`) with plain unit tests.
- **Heavy imports stay inside workers.** No pandas/geopandas at TUI startup —
  preprocess imports happen in the background worker that runs the pipeline.
- **One job at a time.** Pull and preprocess jobs are mutually exclusive.
- **ADR-005 stands.** No cron, no schedulers; staleness is surfaced passively
  (launch sweep + badges). Job-completion notifications are allowed.
- **Deploy is confirm-gated and data-only.** Dry-run shown before apply; a
  failed verify blocks deploy pending an explicit, logged override; restart
  strictly after the sync leg (never mid-sync). Code deploys stay a dev workflow.
- Textual `Widget._render` is internal — screens repaint via their own
  `_repaint` helpers.

## Testing
Pure modules via plain pytest; app behavior via Textual pilot tests
(`tests/test_data_tui.py`, stdlib `asyncio.run` — no pytest-asyncio).
The deploy driver is contract-tested against a stub script.

## Related context
- The headless engine this drives: [`../fetch/AGENTS.md`](../fetch/AGENTS.md)
- What preprocess produces: [`../preprocess/AGENTS.md`](../preprocess/AGENTS.md)
