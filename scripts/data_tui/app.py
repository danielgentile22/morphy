"""The Textual app: sources table, check sweep, and the pull flow.

Slice 2 (#236) makes pulls real: pull-now / pull-all-stale run through the
existing ``fetch.puller.fetch_one`` in a background worker thread (one job
at a time, sources sequential) with a throttled byte/speed progress line,
so the UI stays interactive through a 4 GB pull. Resume comes free from
the fetch layer (``supports_resume`` sources keep their ``.partial/``).
Failures surface in a detail pane fed by the manifest's structured
``last_error``, the session activity log filters all / errors / per-source,
and job completion fires a desktop notification (``notify.send``).
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime

from fetch import registry
from fetch.base import CATEGORY_ORDER, DataSource
from fetch.manifest import Manifest, SourceEntry
from fetch.puller import CheckOutcome, FetchOutcome, check_one, fetch_one
from fetch.storage import human_bytes
from rich.text import Text
from textual.app import App, ComposeResult
from textual.widgets import DataTable, Footer, Header, Static

from .freshness import Badge, attention_items, badge_for
from .notify import send as notify_send

BADGE_STYLES = {
    "fresh": "bold green",
    "due_soon": "bold yellow",
    "stale": "bold red",
    "missing": "dim",
    "dead": "bold white on red",
    "manual": "magenta",
    "deferred": "dim italic",
}

_CHECK_POOL_SIZE = 8  # matches the "cheap probe" contract; 16 sources ≈ 2 rounds
_FAILED_STATUSES = ("check_failed", "fetch_failed")
_PROGRESS_MIN_INTERVAL = 0.25  # seconds between progress-line repaints
_LOG_FILTERS = ("all", "errors", "source")
_LOG_SHOWN = 30  # most recent events rendered in the log pane


def _badge_text(badge: Badge) -> Text:
    return Text(badge.label, style=BADGE_STYLES[badge.kind])


@dataclass(frozen=True)
class ActivityEvent:
    at: str  # HH:MM:SS
    source_id: str
    message: str
    error: bool


def filter_activity(
    events: list[ActivityEvent], mode: str, source_id: str | None = None
) -> list[ActivityEvent]:
    """Pure filter behind the activity-log pane: all / errors / per-source."""
    if mode == "errors":
        return [e for e in events if e.error]
    if mode == "source":
        return [e for e in events if e.source_id == source_id]
    return list(events)


class DataTuiApp(App):
    """Sources table grouped by category, freshness badges, pulls, activity log."""

    TITLE = "Pilot Data"
    BINDINGS = [
        ("c", "check_updates", "Check"),
        ("p", "pull_now", "Pull"),
        ("P", "pull_stale", "Pull stale"),
        ("l", "toggle_log", "Log"),
        ("f", "cycle_log_filter", "Log filter"),
        ("d", "diagnose", "Diagnose"),
        ("q", "quit", "Quit"),
    ]
    CSS = """
    #attention {
        height: auto;
        max-height: 12;
        margin: 0 1;
        padding: 0 1;
        border: round $warning;
    }
    #job {
        height: auto;
        margin: 0 1;
        color: $accent;
    }
    #sources {
        height: 1fr;
        margin: 0 1;
    }
    #detail {
        height: auto;
        max-height: 14;
        margin: 0 1;
        padding: 0 1;
        border: round $error;
    }
    #log {
        height: auto;
        max-height: 12;
        margin: 0 1;
        padding: 0 1;
        border: round $primary;
    }
    """

    def __init__(
        self,
        sources: list[DataSource] | None = None,
        deferred: list[DataSource] | None = None,
        manifest: Manifest | None = None,
    ) -> None:
        super().__init__()
        self.sources = sources if sources is not None else registry.all_sources()
        self.deferred = deferred if deferred is not None else registry.deferred_sources()
        self._by_id = {s.id: s for s in (*self.sources, *self.deferred)}
        self._deferred_ids = {s.id for s in self.deferred}
        self._persist = manifest is None  # injected manifest (tests) never saves to disk
        self.manifest = manifest if manifest is not None else Manifest.load()
        self._sweep_running = False
        self._pull_running = False
        self._diagnose_running = False
        self._diagnose_for: str | None = None
        self._diagnose_text = ""
        self._selected_source_id: str | None = None
        self._log_filter = "all"
        self._log_visible = False
        self.activity: list[ActivityEvent] = []
        # Plain-text mirrors asserted on by pilot tests (Static's content
        # API differs across Textual majors).
        self.attention_lines: list[str] = []
        self.job_lines: list[str] = []
        self.detail_lines: list[str] = []
        self.log_lines: list[str] = []

    # ── layout ──────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="attention")
        yield Static(id="job")
        yield DataTable(id="sources")
        yield Static(id="detail")
        yield Static(id="log")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#detail", Static).display = False
        self.query_one("#log", Static).display = False
        table = self.query_one(DataTable)
        table.cursor_type = "row"
        for label, key in [
            ("Source", "source"),
            ("Coverage", "coverage"),
            ("Cadence", "cadence"),
            ("Status", "status"),
            ("Fetched", "fetched"),
            ("Checked", "checked"),
        ]:
            table.add_column(label, key=key)
        self._build_rows(table)
        self._refresh_attention()

    def _build_rows(self, table: DataTable) -> None:
        by_cat: dict[str, list[DataSource]] = {}
        for s in self.sources:
            by_cat.setdefault(s.category, []).append(s)
        cats = [c for c in CATEGORY_ORDER if c in by_cat]
        cats += [c for c in by_cat if c not in CATEGORY_ORDER]
        for cat in cats:
            table.add_row(Text(cat.upper(), style="bold"), "", "", "", "", "", key=f"cat:{cat}")
            for s in sorted(by_cat[cat], key=lambda s: s.name.lower()):
                table.add_row(*self._row_cells(s), key=s.id)
        if self.deferred:
            table.add_row(
                Text("DEFERRED", style="bold dim"), "", "", "", "", "", key="cat:deferred"
            )
            for s in sorted(self.deferred, key=lambda s: s.name.lower()):
                table.add_row(*self._row_cells(s, deferred=True), key=s.id)

    def _row_cells(self, s: DataSource, *, deferred: bool = False) -> tuple:
        e = self.manifest.entry(s.id)
        badge = badge_for(s, e, deferred=deferred)
        return (
            f"  {s.name}",
            s.coverage,
            f"{s.update_cadence_days}d" if s.update_cadence_days else "—",
            _badge_text(badge),
            (e.fetched_at or "—")[:10],
            (e.checked_at or "—")[:10],
        )

    # ── attention panel ─────────────────────────────────────────────────

    def _refresh_attention(self) -> None:
        items = attention_items(self.sources, self.manifest)
        panel = self.query_one("#attention", Static)
        if not items:
            self.attention_lines = ["✓ All sources current"]
            panel.update(Text("✓ All sources current", style="bold green"))
            return
        self.attention_lines = [f"⚠ {len(items)} sources need attention"] + [
            f"{it.name} — {it.reason}" for it in items
        ]
        body = Text(self.attention_lines[0], style="bold yellow")
        for it in items:
            body.append(f"\n  {it.name}", style="bold")
            body.append(f" — {it.reason}", style="dim")
        panel.update(body)

    def _refresh_source_row(self, source: DataSource, *, deferred: bool = False) -> None:
        table = self.query_one(DataTable)
        cells = self._row_cells(source, deferred=deferred)
        for key, value in zip(
            ("source", "coverage", "cadence", "status", "fetched", "checked"), cells
        ):
            table.update_cell(source.id, key, value)
        self._refresh_attention()

    # ── selection + failure-detail pane ─────────────────────────────────

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        key = event.row_key.value if event.row_key else None
        self._selected_source_id = key if key and not key.startswith("cat:") else None
        self._refresh_detail()

    def _refresh_detail(self) -> None:
        pane = self.query_one("#detail", Static)
        sid = self._selected_source_id
        entry = self.manifest.sources.get(sid) if sid else None
        if sid is None or entry is None or entry.status not in _FAILED_STATUSES:
            self.detail_lines = []
            pane.display = False
            return
        source = self._by_id.get(sid)
        name = source.name if source else sid
        le = entry.last_error or {}
        elapsed = le.get("elapsed")
        lines = [
            f"✗ {name} — {entry.status.replace('_', ' ')}",
            f"URL: {le.get('url') or '—'}",
            f"Error: {le.get('error') or entry.error or '—'}",
            f"Elapsed: {f'{elapsed}s' if elapsed is not None else '—'}",
            f"Failed at: {le.get('at') or entry.checked_at or '—'}",
            f"Last successful fetch: {entry.fetched_at or 'never'}",
        ]
        if self._diagnose_for == sid:
            if self._diagnose_text:
                lines += ["── diagnosis ──", *self._diagnose_text.strip().splitlines()]
            elif self._diagnose_running:
                lines.append("Asking Claude to diagnose…")
        self.detail_lines = lines
        body = Text(lines[0], style="bold red")
        for line in lines[1:]:
            body.append(f"\n{line}")
        pane.update(body)
        pane.display = True

    # ── activity log ────────────────────────────────────────────────────

    def _log_activity(self, source_id: str, message: str, error: bool = False) -> None:
        at = datetime.now(UTC).strftime("%H:%M:%S")
        self.activity.append(ActivityEvent(at, source_id, message, error))
        self._refresh_log()

    def action_toggle_log(self) -> None:
        self._log_visible = not self._log_visible
        self.query_one("#log", Static).display = self._log_visible
        self._refresh_log()

    def action_cycle_log_filter(self) -> None:
        nxt = _LOG_FILTERS[(_LOG_FILTERS.index(self._log_filter) + 1) % len(_LOG_FILTERS)]
        if nxt == "source" and self._selected_source_id is None:
            nxt = "all"
        self._log_filter = nxt
        if not self._log_visible:
            self.action_toggle_log()
            return
        self._refresh_log()

    def _refresh_log(self) -> None:
        label = self._log_filter
        if label == "source":
            label = f"source: {self._selected_source_id}"
        shown = filter_activity(self.activity, self._log_filter, self._selected_source_id)
        self.log_lines = [f"Activity ({label}) — {len(shown)} events"] + [
            f"{e.at} {e.source_id}: {e.message}" for e in shown[-_LOG_SHOWN:]
        ]
        if not self._log_visible:
            return
        body = Text(self.log_lines[0], style="bold")
        for e in shown[-_LOG_SHOWN:]:
            body.append(f"\n{e.at} ", style="dim")
            body.append(f"{e.source_id}: {e.message}", style="red" if e.error else "")
        self.query_one("#log", Static).update(body)

    # ── check-for-updates sweep ─────────────────────────────────────────

    def action_check_updates(self) -> None:
        if self._sweep_running:
            return
        self._sweep_running = True
        self.sub_title = "checking for updates…"
        self.run_worker(self._sweep, thread=True)

    def _sweep(self) -> None:
        """Thread worker: probe all checkable sources in parallel."""
        checkable = [
            s
            for s in self.sources
            if not s.is_manual_only and (not s.needs_credentials or s.credentials_available())
        ]
        # Pre-seed entries on this thread so pool threads only mutate their
        # own (disjoint) SourceEntry objects — no shared-dict inserts.
        for s in checkable:
            self.manifest.entry(s.id)
        with ThreadPoolExecutor(max_workers=_CHECK_POOL_SIZE) as pool:
            futures = {pool.submit(check_one, s, self.manifest): s for s in checkable}
            for future in as_completed(futures):
                self.call_from_thread(self._check_done, futures[future], future.result())
        self.manifest.set_last_full_check()
        if self._persist:
            self.manifest.save()
        self._sweep_running = False
        self.call_from_thread(self._sweep_done)

    def _check_done(self, source: DataSource, out: CheckOutcome) -> None:
        if out.ok:
            self._log_activity(source.id, f"check ok — remote {out.remote_version or '—'}")
        else:
            self._log_activity(source.id, f"check failed — {out.error}", error=True)
        self._refresh_source_row(source)
        self._refresh_detail()

    def _sweep_done(self) -> None:
        self.sub_title = f"checked {self.manifest.last_full_check or ''}"

    # ── pull jobs ───────────────────────────────────────────────────────

    def action_pull_now(self) -> None:
        sid = self._selected_source_id
        source = self._by_id.get(sid) if sid else None
        if source is None or sid in self._deferred_ids:
            return
        if source.is_manual_only:
            self._job_update(f"{source.name} is manual-only — no automated pull.")
            return
        if source.needs_credentials and not source.credentials_available():
            self._job_update(f"{source.name} needs credentials — skipped.")
            return
        self._start_pull([source])

    def action_pull_stale(self) -> None:
        targets = [
            s
            for s in self.sources
            if badge_for(s, self.manifest.entry(s.id)).kind in ("stale", "missing")
            and not s.is_manual_only
            and (not s.needs_credentials or s.credentials_available())
        ]
        if not targets:
            self._job_update("Nothing stale to pull.")
            return
        self._start_pull(targets)

    def _start_pull(self, targets: list[DataSource]) -> None:
        if self._pull_running:
            return
        self._pull_running = True
        # Pre-seed entries on the app thread — pool/worker threads must
        # never insert into the shared sources dict (same rule as _sweep).
        for s in targets:
            self.manifest.entry(s.id)
        self.run_worker(lambda: self._pull_worker(targets), thread=True)

    def _pull_worker(self, targets: list[DataSource]) -> None:
        """Thread worker: pull sources sequentially (PRD #233 story 5)."""
        results: list[FetchOutcome] = []
        for i, s in enumerate(targets, 1):
            self.call_from_thread(self._job_update, f"[{i}/{len(targets)}] {s.name} — starting…")
            self.call_from_thread(self._log_activity, s.id, "fetch started", False)
            out = fetch_one(s, self.manifest, self._make_progress(s, i, len(targets)))
            results.append(out)
            if self._persist:
                self.manifest.save()
            self.call_from_thread(self._pull_source_done, s, out)
        self.call_from_thread(self._pull_all_done, results)

    def _make_progress(self, source: DataSource, idx: int, n: int):
        """Byte/speed progress callback, throttled so the app thread isn't
        flooded by 64 KiB-chunk updates. Runs on the pull worker thread."""
        state = {"t": time.monotonic(), "b": 0, "ui": 0.0}

        def cb(done: int, total: int | None, label: str) -> None:
            now = time.monotonic()
            final = total is not None and done >= total
            if now - state["ui"] < _PROGRESS_MIN_INTERVAL and not final:
                return
            speed = None
            dt = now - state["t"]
            if done >= state["b"] and dt > 0:
                speed = (done - state["b"]) / dt
            state["t"], state["b"], state["ui"] = now, done, now
            line = f"[{idx}/{n}] {source.name}: {human_bytes(done)}"
            if total:
                line += f" / {human_bytes(total)}"
            if speed:
                line += f" ({human_bytes(int(speed))}/s)"
            if label:
                line += f" — {label}"
            self.call_from_thread(self._job_update, line)

        return cb

    def _job_update(self, line: str) -> None:
        self.job_lines.append(line)
        self.query_one("#job", Static).update(Text(line))

    def _pull_source_done(self, source: DataSource, out: FetchOutcome) -> None:
        if out.ok and not out.skipped:
            self._log_activity(source.id, f"fetch ok — {human_bytes(out.bytes)}")
        elif out.skipped:
            self._log_activity(source.id, f"fetch skipped — {out.skip_reason}")
        else:
            self._log_activity(source.id, f"fetch failed — {out.error}", error=True)
        self._refresh_source_row(source)
        self._refresh_detail()

    def _pull_all_done(self, results: list[FetchOutcome]) -> None:
        self._pull_running = False
        pulled = sum(1 for r in results if r.ok and not r.skipped)
        failed = [r for r in results if not r.ok]
        if failed:
            summary = f"✗ pull finished — {pulled} ok, {len(failed)} failed"
            detail = "; ".join(f"{r.source_id}: {r.error}" for r in failed)
            notify_send("Pilot Data — pull failed", f"{pulled} ok, {len(failed)} failed. {detail}")
        else:
            summary = f"✓ pull finished — {pulled} pulled"
            notify_send("Pilot Data — pull complete", f"{pulled} source(s) pulled.")
        self._job_update(summary)
        self.sub_title = summary

    # ── diagnose-with-AI ────────────────────────────────────────────────

    def action_diagnose(self) -> None:
        sid = self._selected_source_id
        entry = self.manifest.sources.get(sid) if sid else None
        if (
            sid is None
            or entry is None
            or entry.status not in _FAILED_STATUSES
            or self._diagnose_running
        ):
            return
        self._diagnose_running = True
        self._diagnose_for = sid
        self._diagnose_text = ""
        self._refresh_detail()
        self.run_worker(lambda: self._diagnose_worker(sid, entry), thread=True)

    def _diagnose_worker(self, sid: str, entry: SourceEntry) -> None:
        try:
            from diagnose import diagnose
            from verify_raw import VerifyResult

            detail = (entry.last_error or {}).get("error") or entry.error or "unknown failure"
            vr = VerifyResult(
                source_id=sid,
                verdict="FAIL",
                nbytes=entry.bytes,
                detail=f"{entry.status}: {detail}",
            )
            diagnose(vr, on_chunk=lambda c: self.call_from_thread(self._append_diagnose, sid, c))
        except Exception as ex:  # noqa: BLE001 — DiagnoseUnavailable, missing SDK, network
            self.call_from_thread(self._append_diagnose, sid, f"⚠ diagnose unavailable: {ex}")
        finally:
            self._diagnose_running = False

    def _append_diagnose(self, sid: str, chunk: str) -> None:
        if self._diagnose_for != sid:
            return  # selection moved on; drop the stream
        self._diagnose_text += chunk
        self._refresh_detail()
