"""User-management CLI for the credential table (#87, PRD #83; DB-backed
since PRD #130).

The administrator's surface for credentials — never generate, paste, or read
a hash by hand:

    cd backend && python -m app.users add <username> <team>     # hidden password prompt
    cd backend && python -m app.users add <username> <team> --read-only
    cd backend && python -m app.users remove <username>
    cd backend && python -m app.users list
    cd backend && python -m app.users set-password <username>   # hidden password prompt
    cd backend && python -m app.users set-team <username> <team>
    cd backend && python -m app.users set-read-only <username> on|off
    cd backend && python -m app.users import-file <path>        # one-shot users.txt migration

    The same subcommands as the file era, now writing the ``credential``
table in the app database (``DATABASE_URL``, same default as the backend —
on the Fly machine that's the volume DB Litestream replicates). Changes are
authoritative on the user's next request (ADR-063 per-request authority,
storage amended by PRD #130). The CLI never prints a password or a hash.

``import-file`` migrates a ``username:hash:team`` users.txt in file order
(so the first team keeps tenant 1, #86) and refuses to run over a non-empty
table — it is a cutover, never a merge.

The command functions live in ``credentials_store``; this module is the
argparse/getpass shell plus the thin re-exports the API routes use.
"""

from __future__ import annotations

import argparse
import enum
import sys
from pathlib import Path

from sqlalchemy.orm import Session

from . import credentials, credentials_store
from .credentials_store import CredentialsError


class ChangePasswordOutcome(enum.Enum):
    """The result of a self-service password change (PRD #121). ``WRONG_CURRENT``
    is the only *soft* failure (nothing written); a missing user or an empty new
    password raise ``CredentialsError`` like the rest of the store."""

    OK = "ok"
    WRONG_CURRENT = "wrong_current"


def change_password(
    session: Session, username: str, current: str, new: str
) -> ChangePasswordOutcome:
    """Self-service password change (PRD #121): verify ``current``, then rotate.

    The one sanctioned runtime caller of the store's password writer. A wrong
    current password returns ``WRONG_CURRENT`` and writes nothing."""
    if credentials_store.change_password(session, username, current, new):
        return ChangePasswordOutcome.OK
    return ChangePasswordOutcome.WRONG_CURRENT


# ── CLI shell ─────────────────────────────────────────────────────────────────
def _prompt_password() -> str:  # pragma: no cover - interactive prompt
    import getpass

    password = getpass.getpass("Password: ")
    if not password:
        raise CredentialsError("password must not be empty")
    if getpass.getpass("Confirm: ") != password:
        raise CredentialsError("passwords do not match")
    return password


def _main(argv: list[str]) -> int:  # pragma: no cover - thin argparse/getpass shell
    parser = argparse.ArgumentParser(
        prog="python -m app.users",
        description="Manage backend credentials (the credential table in the app DB).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="add a user (prompts for a password)")
    p_add.add_argument("username")
    p_add.add_argument("team")
    p_add.add_argument(
        "--read-only",
        action="store_true",
        help="the user can sign in and read, but every write is refused (ADR-077)",
    )

    p_remove = sub.add_parser("remove", help="remove a user")
    p_remove.add_argument("username")

    sub.add_parser("list", help="list usernames and teams (never hashes)")

    p_setpw = sub.add_parser("set-password", help="change a user's password (prompts)")
    p_setpw.add_argument("username")

    p_setteam = sub.add_parser("set-team", help="move a user to a different team")
    p_setteam.add_argument("username")
    p_setteam.add_argument("team")

    p_ro = sub.add_parser("set-read-only", help="flag or unflag a user as read-only")
    p_ro.add_argument("username")
    p_ro.add_argument("state", choices=["on", "off"])

    p_import = sub.add_parser(
        "import-file",
        help="one-shot migration: import a users.txt (username:hash:team lines) in file order",
    )
    p_import.add_argument("path")

    args = parser.parse_args(argv[1:])

    # Imported here (not module top) so `--help` and argument errors never
    # touch the database.
    from .db import SessionLocal, init_db

    init_db()  # the credential table must exist before any command

    try:
        with SessionLocal() as session:
            if args.command == "add":
                credentials_store.add(
                    session,
                    args.username,
                    args.team,
                    _prompt_password(),
                    read_only=args.read_only,
                )
                print(
                    f"added '{credentials.normalize(args.username)}' "
                    f"to team '{credentials.normalize(args.team)}'"
                    + (" (read-only)" if args.read_only else "")
                )
            elif args.command == "remove":
                credentials_store.remove(session, args.username)
                print(f"removed '{credentials.normalize(args.username)}'")
            elif args.command == "list":
                entries = credentials_store.list_users(session)
                if not entries:
                    print("no users")
                else:
                    width = max(len(u) for u, _, _ in entries)
                    for username, team, read_only in entries:
                        print(
                            f"{username:<{width}}  {team}" + ("  (read-only)" if read_only else "")
                        )
            elif args.command == "set-password":
                credentials_store.set_password(session, args.username, _prompt_password())
                print(f"password updated for '{credentials.normalize(args.username)}'")
            elif args.command == "set-team":
                credentials_store.set_team(session, args.username, args.team)
                print(
                    f"'{credentials.normalize(args.username)}' moved "
                    f"to team '{credentials.normalize(args.team)}'"
                )
            elif args.command == "set-read-only":
                credentials_store.set_read_only(session, args.username, args.state == "on")
                print(f"'{credentials.normalize(args.username)}' read-only: {args.state}")
            elif args.command == "import-file":
                entries = list(credentials.load(Path(args.path)).values())
                if not entries:
                    raise CredentialsError(f"no valid credential lines in {args.path}")
                n = credentials_store.import_entries(session, entries)
                print(f"imported {n} user(s) from {args.path}")
    except CredentialsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(_main(sys.argv))
