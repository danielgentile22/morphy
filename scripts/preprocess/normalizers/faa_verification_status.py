"""FAA DOF verification-status code → text lookup (audit fix E8).

The FAA Digital Obstacle File carries a single-character ``verification_status``
that says whether the obstacle's position/height was verified by the FAA's
Obstacle Data Team. The normalizer collapsed it to a binary "Verified" (for a
code that was even wrong — it tested ``"V"``, but the verified code is ``"O"``)
vs "Other", erasing the real distinction.

Pure + isolated by design so the decoding is unit-testable without fixtures.
An unrecognized code degrades predictably — it returns the bare code rather
than silently flattening to "Other".

Source: FAA DOF README / FAQ (the verification-status field is "O" Verified /
"U" Unverified).
"""

from __future__ import annotations

VERIFICATION_STATUS: dict[str, str] = {
    "O": "Verified",
    "U": "Unverified",
}


def verification_status_desc(code: object) -> str | None:
    """Decode an FAA DOF verification-status code to its text.

    Returns None for blank/missing. An unknown code returns the bare code
    (uppercased) — predictable degradation, never a silent "Other".
    """
    if code is None:
        return None
    s = str(code).strip().upper()
    if not s:
        return None
    return VERIFICATION_STATUS.get(s, s)
