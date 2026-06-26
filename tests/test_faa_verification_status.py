"""FAA DOF verification-status lookup (audit fix E8)."""

from __future__ import annotations

from preprocess.normalizers.faa_verification_status import verification_status_desc


def test_documented_codes_map_to_faithful_text():
    assert verification_status_desc("O") == "Verified"
    assert verification_status_desc("U") == "Unverified"
    assert verification_status_desc("o") == "Verified"  # case-insensitive


def test_unknown_code_degrades_predictably_not_to_other():
    # The bug it replaces collapsed everything-but-"V" to "Other". An
    # unrecognized code now comes back as the bare code, never "Other".
    assert verification_status_desc("V") == "V"
    assert verification_status_desc("X") == "X"


def test_blank_and_missing_return_none():
    assert verification_status_desc("") is None
    assert verification_status_desc("  ") is None
    assert verification_status_desc(None) is None
