"""Centralised palette + dark-mode detection for the puller UI.

Both the main window and the modal dialogs need light/dark hex pairs for
the same handful of semantic roles (muted text, body text, success,
failure, warning, link). Three near-identical sets of `_muted_hex` /
`_ok_hex` / `_fail_hex` methods grew up across `main_window.py`,
`preprocess_dialog.py`, and `walkthrough_dialog.py`; this module is the
single source of truth.

Some callers (main window) derive dark-mode from their own palette;
others (dialogs) accept a `dark_mode` flag from the caller. Both work
through ``Palette.for_dark()`` / ``Palette.for_widget()``.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QWidget


def is_dark(widget: QWidget) -> bool:
    """Heuristic: window background lightness < 128 ⇒ dark mode."""
    return widget.palette().color(QPalette.Window).lightness() < 128


@dataclass(frozen=True)
class Palette:
    """Semantic colour roles for the puller UI."""

    muted: str
    text: str
    ok: str
    fail: str
    warn: str
    link: str

    @classmethod
    def for_dark(cls, dark: bool) -> "Palette":
        if dark:
            return cls(
                muted="#bdbdbd",
                text="#eeeeee",
                ok="#81c784",
                fail="#e57373",
                warn="#ffd54f",
                link="#64b5f6",
            )
        return cls(
            muted="#616161",
            text="#212121",
            ok="#2e7d32",
            fail="#c62828",
            warn="#f57c00",
            link="#1565c0",
        )

    @classmethod
    def for_widget(cls, widget: QWidget) -> "Palette":
        return cls.for_dark(is_dark(widget))
