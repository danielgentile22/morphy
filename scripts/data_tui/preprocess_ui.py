"""Preprocess stage screen (#238): pick states, preseeded by the planner.

Pure shell — the preselection comes from ``planner.plan_refresh`` and the
pipeline run happens in ``app.py``'s background worker; this screen only
collects the state selection and dismisses with the chosen FIPS list.
"""

from __future__ import annotations

from preprocess.geographies import STATES
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Footer, SelectionList, Static
from textual.widgets.selection_list import Selection


class PreprocessScreen(ModalScreen[list[str] | None]):
    """Select states to compose; dismisses with the selected FIPS list."""

    BINDINGS = [
        ("s", "start", "Start preprocess"),
        ("escape", "cancel", "Cancel"),
    ]
    CSS = """
    PreprocessScreen { align: center middle; }
    #pre-box {
        width: 70%;
        height: auto;
        max-height: 80%;
        padding: 1 2;
        border: round $primary;
        background: $surface;
    }
    #pre-error { color: $error; }
    """

    def __init__(
        self,
        candidates: list[str],
        preselected: list[str],
        deploy_warranted: bool = False,
    ) -> None:
        super().__init__()
        self.candidates = candidates
        self.preselected = set(preselected)
        self.deploy_warranted = deploy_warranted
        self.lines: list[str] = []  # plain-text mirror for Textual Pilot tests

    def compose(self) -> ComposeResult:
        self.lines = ["Preprocess — normalize all sources, then compose the selected states"]
        header = Text(self.lines[0], style="bold")
        if self.deploy_warranted:
            hint = "Composites are older than pulled data — deploy after this run."
            self.lines.append(hint)
            header.append(f"\n{hint}", style="yellow")
        header.append("\n[space] toggle   [s] start   [esc] cancel", style="dim")
        with Vertical(id="pre-box"):
            yield Static(header)
            yield SelectionList[str](
                *[
                    Selection(f"{STATES[f].abbr} — {STATES[f].name}", f, f in self.preselected)
                    for f in self.candidates
                    if f in STATES
                ]
            )
            yield Static(id="pre-error")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one(SelectionList).focus()

    def action_start(self) -> None:
        selected = list(self.query_one(SelectionList).selected)
        if not selected:
            self.query_one("#pre-error", Static).update("Select at least one state.")
            return
        self.dismiss(sorted(selected))

    def action_cancel(self) -> None:
        self.dismiss(None)
