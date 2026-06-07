"""User-management CLI for the credentials file (#87, PRD #83).

The administrator's surface for users.txt — never generate, paste, or read
a hash by hand:

    cd backend && python -m app.users add <username> <team>     # hidden password prompt
    cd backend && python -m app.users remove <username>
    cd backend && python -m app.users list
    cd backend && python -m app.users set-password <username>   # hidden password prompt
    cd backend && python -m app.users set-team <username> <team>

The file defaults to ``backend/users.txt``; override with ``--file`` or the
``APP_USERS_FILE`` env var (same variable the backend reads). Writes are
atomic (temp file + rename, the repo-wide convention) and preserve comments
and line order — order matters, because the first team in the file owns
tenant 1 (#86). The CLI never prints a password or a hash.

Deliberately does NOT import ``config``: building Settings runs the
fail-closed boot check, and ``add`` is how the very file that check
requires gets created in the first place.
"""

from __future__ import annotations

import argparse
import enum
import os
import sys
import tempfile
from pathlib import Path

from . import credentials
from .password import hash_password, verify_password

# backend/app/users.py → parents[1] = backend/
DEFAULT_FILE = Path(__file__).resolve().parents[1] / "users.txt"


class UsersFileError(Exception):
    """A user-facing CLI error (bad input, missing user, duplicate)."""


class ChangePasswordOutcome(enum.Enum):
    """The result of a self-service password change (PRD #121). ``WRONG_CURRENT``
    is the only *soft* failure (the file is left untouched); a missing user or an
    empty new password raise ``UsersFileError`` like the rest of this module."""

    OK = "ok"
    WRONG_CURRENT = "wrong_current"


# ── public command functions (the testable API) ──────────────────────────────
def add_user(file: Path | str, username: str, team: str, password: str) -> None:
    """Append a new credential line. The new user can sign in immediately."""
    username_n, team_n = _valid_username(username), _valid_team(team)
    if not password:
        raise UsersFileError("password must not be empty")
    lines = _read_lines(file)
    if _find_user_line(lines, username_n) is not None:
        raise UsersFileError(
            f"user '{username_n}' already exists (use set-password / set-team to change it)"
        )
    lines.append(f"{username_n}:{hash_password(password)}:{team_n}")
    _write_atomic(file, lines)


def remove_user(file: Path | str, username: str) -> None:
    """Delete a user's line. Their next sign-in attempt fails."""
    lines = _read_lines(file)
    idx = _require_user_line(lines, username)
    del lines[idx]
    _write_atomic(file, lines)


def list_users(file: Path | str) -> list[tuple[str, str]]:
    """``(username, team)`` pairs in file order — never passwords or hashes."""
    return [(e.username, e.team) for e in credentials.load(Path(file)).values()]


def set_password(file: Path | str, username: str, password: str) -> None:
    """Replace a user's hash in place (their line keeps its position)."""
    if not password:
        raise UsersFileError("password must not be empty")
    lines = _read_lines(file)
    idx = _require_user_line(lines, username)
    entry = _entry_of(lines[idx])
    lines[idx] = f"{entry.username}:{hash_password(password)}:{entry.team}"
    _write_atomic(file, lines)


def change_password(
    file: Path | str, username: str, current: str, new: str
) -> ChangePasswordOutcome:
    """Self-service password change (PRD #121): verify ``current``, then rotate.

    The one *sanctioned* runtime caller of ``set_password`` — it never writes a
    line by hand. The current password is checked first (constant-time) so a
    wrong guess returns ``WRONG_CURRENT`` and leaves the file byte-for-byte
    unchanged. On success ``set_password`` does the atomic rewrite, preserving
    the user's team + file position and bumping mtime so the per-request
    ``CredentialsFile`` cache reloads. An empty ``new`` (or an unknown user)
    raises ``UsersFileError``."""
    lines = _read_lines(file)
    idx = _require_user_line(lines, username)
    entry = _entry_of(lines[idx])
    if not verify_password(current, entry.encoded_hash):
        return ChangePasswordOutcome.WRONG_CURRENT
    set_password(file, username, new)
    return ChangePasswordOutcome.OK


def set_team(file: Path | str, username: str, team: str) -> None:
    """Move a user to another team (their line keeps its position)."""
    team_n = _valid_team(team)
    lines = _read_lines(file)
    idx = _require_user_line(lines, username)
    entry = _entry_of(lines[idx])
    lines[idx] = f"{entry.username}:{entry.encoded_hash}:{team_n}"
    _write_atomic(file, lines)


# ── helpers ───────────────────────────────────────────────────────────────────
def _valid_username(username: str) -> str:
    name = credentials.normalize(username)
    if not name:
        raise UsersFileError("username must not be empty")
    if ":" in name:
        raise UsersFileError("username must not contain ':' (the field separator)")
    return name


def _valid_team(team: str) -> str:
    name = credentials.normalize(team)
    if not name:
        raise UsersFileError("team must not be empty")
    if ":" in name:
        raise UsersFileError("team must not contain ':' (the field separator)")
    return name


def _read_lines(file: Path | str) -> list[str]:
    path = Path(file)
    if not path.is_file():
        return []
    return path.read_text(encoding="utf-8").splitlines()


def _write_atomic(file: Path | str, lines: list[str]) -> None:
    """Temp file + rename in the same directory — a crash mid-write can never
    truncate or corrupt the live file, and no temp file with hash material
    is ever left behind."""
    path = Path(file)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".users-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + ("\n" if lines else ""))
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _find_user_line(lines: list[str], username: str) -> int | None:
    """Index of the credential line for ``username`` (normalized), or None."""
    canonical = credentials.normalize(username)
    for i, line in enumerate(lines):
        entry = credentials.parse(line)
        if canonical in entry:
            return i
    return None


def _require_user_line(lines: list[str], username: str) -> int:
    idx = _find_user_line(lines, username)
    if idx is None:
        raise UsersFileError(f"no user '{credentials.normalize(username)}' in the file")
    return idx


def _entry_of(line: str) -> credentials.CredentialEntry:
    return next(iter(credentials.parse(line).values()))


# ── CLI shell ─────────────────────────────────────────────────────────────────
def _resolve_file(arg: str | None) -> Path:
    if arg:
        return Path(arg)
    env = os.environ.get("APP_USERS_FILE")
    return Path(env) if env else DEFAULT_FILE


def _prompt_password() -> str:  # pragma: no cover - interactive prompt
    import getpass

    password = getpass.getpass("Password: ")
    if not password:
        raise UsersFileError("password must not be empty")
    if getpass.getpass("Confirm: ") != password:
        raise UsersFileError("passwords do not match")
    return password


def _main(argv: list[str]) -> int:  # pragma: no cover - thin argparse/getpass shell
    parser = argparse.ArgumentParser(
        prog="python -m app.users",
        description="Manage the backend credentials file (users.txt).",
    )
    parser.add_argument("--file", help="path to the credentials file (default: backend/users.txt)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="add a user (prompts for a password)")
    p_add.add_argument("username")
    p_add.add_argument("team")

    p_remove = sub.add_parser("remove", help="remove a user")
    p_remove.add_argument("username")

    sub.add_parser("list", help="list usernames and teams (never hashes)")

    p_setpw = sub.add_parser("set-password", help="change a user's password (prompts)")
    p_setpw.add_argument("username")

    p_setteam = sub.add_parser("set-team", help="move a user to a different team")
    p_setteam.add_argument("username")
    p_setteam.add_argument("team")

    args = parser.parse_args(argv[1:])
    file = _resolve_file(args.file)

    try:
        if args.command == "add":
            add_user(file, args.username, args.team, _prompt_password())
            print(
                f"added '{credentials.normalize(args.username)}' "
                f"to team '{credentials.normalize(args.team)}' in {file}"
            )
        elif args.command == "remove":
            remove_user(file, args.username)
            print(f"removed '{credentials.normalize(args.username)}' from {file}")
        elif args.command == "list":
            entries = list_users(file)
            if not entries:
                print(f"no users in {file}")
            else:
                width = max(len(u) for u, _ in entries)
                for username, team in entries:
                    print(f"{username:<{width}}  {team}")
        elif args.command == "set-password":
            set_password(file, args.username, _prompt_password())
            print(f"password updated for '{credentials.normalize(args.username)}'")
        elif args.command == "set-team":
            set_team(file, args.username, args.team)
            print(
                f"'{credentials.normalize(args.username)}' moved "
                f"to team '{credentials.normalize(args.team)}'"
            )
    except UsersFileError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(_main(sys.argv))
