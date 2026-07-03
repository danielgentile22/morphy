"""The Textual app: attention panel + grouped sources table + check sweep.

Read-only in this slice (#234) — no pulls. The sweep runs each source's
``remote_version()`` probe through the existing ``fetch.puller.check_one``
in a thread pool so the UI stays responsive; badges refresh per source as
results land.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from fetch import registry
from fetch.base import CATEGORY_ORDER, DataSource
from fetch.manifest import Manifest
from fetch.puller import check_one
from rich.text import Text
from textual.app import App, ComposeResult
from textual.widgets import DataTable, Footer, Header, Static

from .freshness import Badge, attention_items, badge_for

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


def _badge_text(badge: Badge) -> Text:
    return Text(badge.label, style=BADGE_STYLES[badge.kind])


class DataTuiApp(App):
    """Sources table grouped by category, freshness badges, attention on top."""

    TITLE = "Pilot Data"
    BINDINGS = [
        ("c", "check_updates", "Check for updates"),
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
    #sources {
        height: 1fr;
        margin: 0 1;
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
        # ponytail: private registry read — promote to registry.deferred_sources()
        # in slice 2 (#236), when the fetch lib opens for the manifest change.
        self.deferred = deferred if deferred is not None else list(registry._DEFERRED)
        self._persist = manifest is None  # injected manifest (tests) never saves to disk
        self.manifest = manifest if manifest is not None else Manifest.load()
        self._sweep_running = False
        # Plain-text mirror of the attention panel, asserted on by pilot
        # tests (Static's content API differs across Textual majors).
        self.attention_lines: list[str] = []

    # ── layout ──────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="attention")
        yield DataTable(id="sources")
        yield Footer()

    def on_mount(self) -> None:
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
                self.call_from_thread(self._refresh_source_row, futures[future])
        self.manifest.set_last_full_check()
        if self._persist:
            self.manifest.save()
        self._sweep_running = False
        self.call_from_thread(self._sweep_done)

    def _sweep_done(self) -> None:
        self.sub_title = f"checked {self.manifest.last_full_check or ''}"
