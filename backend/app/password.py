"""Password hashing — stdlib PBKDF2-HMAC-SHA256, no third-party dependency.

The encoded form is self-describing so a stored hash carries everything
``verify_password`` needs to re-derive it:

    pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>

Keeping the iteration count *in* the hash lets the cost be raised later
without invalidating already-issued credentials. Verification is
constant-time (``hmac.compare_digest``) and treats any malformed encoding
as a non-match rather than raising — a corrupt ``APP_USERS`` entry must
fail closed, not crash the login route.

Print an encoded hash for an ``APP_USERS`` entry with:

    cd backend && python -m app.password <password>
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import secrets

ALGORITHM = "pbkdf2_sha256"
DEFAULT_ITERATIONS = 240_000


def hash_password(password: str, *, iterations: int = DEFAULT_ITERATIONS) -> str:
    """Hash ``password`` into the self-describing encoded form."""
    salt = secrets.token_bytes(16)  # `secrets`, not `random` — cryptographic salt
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"{ALGORITHM}${iterations}${_b64(salt)}${_b64(derived)}"


def verify_password(password: str, encoded: str) -> bool:
    """Constant-time check of ``password`` against an encoded hash.

    Returns False (never raises) for any malformed/unsupported encoding.
    """
    try:
        algorithm, iterations_s, salt_b64, hash_b64 = encoded.split("$")
        if algorithm != ALGORITHM:
            return False
        iterations = int(iterations_s)
        salt = _unb64(salt_b64)
        expected = _unb64(hash_b64)
    except (ValueError, binascii.Error):
        return False

    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(derived, expected)


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _unb64(text: str) -> bytes:
    # validate=True so stray characters raise rather than being silently dropped.
    return base64.b64decode(text, validate=True)


def _main(argv: list[str]) -> int:
    import getpass

    password = argv[1] if len(argv) > 1 else getpass.getpass("Password: ")
    if not password:
        print("error: empty password")
        return 1
    print(hash_password(password))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    import sys

    raise SystemExit(_main(sys.argv))
