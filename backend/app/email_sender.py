"""Pluggable magic-link delivery.

The sender is an interface so the real transport (SES / Postmark / SMTP)
can drop in with the hosting setup (#16) without touching the auth flow.
Until then the dev/local app uses ``ConsoleEmailSender`` (a stand-in
inbox printed to stdout) and tests use ``RecordingEmailSender`` (captures
links in memory). Neither the app logger nor these senders ever emit a
raw JWT; the magic link necessarily carries its one-time token because
that link *is* the email being delivered.
"""

from __future__ import annotations

from typing import Protocol


class EmailSender(Protocol):
    def send_login_link(self, email: str, link: str) -> None:
        """Deliver a sign-in link to ``email``. Implementations must not
        raise on a well-formed address (a failed send is logged, not
        surfaced to the caller, to avoid leaking which emails exist)."""
        ...


class ConsoleEmailSender:
    """Dev stand-in: prints the link to stdout. Never enable in prod."""

    def send_login_link(self, email: str, link: str) -> None:
        print(f"[dev-email] magic link for {email}: {link}")  # noqa: T201 — dev inbox


class RecordingEmailSender:
    """Test sender: records ``(email, link)`` pairs, no output."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def send_login_link(self, email: str, link: str) -> None:
        self.sent.append((email, link))
