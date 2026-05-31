"""Unit tests for the stdlib PBKDF2 password module (Slice 1 / #76)."""

from __future__ import annotations

from backend.app.password import ALGORITHM, hash_password, verify_password


def test_hash_verifies_its_own_password() -> None:
    encoded = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", encoded)


def test_rejects_a_wrong_password() -> None:
    encoded = hash_password("s3cret")
    assert not verify_password("S3cret", encoded)
    assert not verify_password("", encoded)


def test_salting_makes_two_hashes_of_one_password_differ() -> None:
    a = hash_password("same")
    b = hash_password("same")
    assert a != b
    # ...yet both still verify the original password.
    assert verify_password("same", a)
    assert verify_password("same", b)


def test_encoded_form_is_self_describing() -> None:
    parts = hash_password("x").split("$")
    assert len(parts) == 4
    assert parts[0] == ALGORITHM
    assert parts[1].isdigit()  # iteration count


def test_malformed_encoding_is_rejected_gracefully() -> None:
    for bad in (
        "",
        "garbage",
        "pbkdf2_sha256$onlythree$parts",
        "other_algo$240000$c2FsdA==$aGFzaA==",
        "pbkdf2_sha256$notanumber$c2FsdA==$aGFzaA==",
        "pbkdf2_sha256$240000$!!!$!!!",
    ):
        assert verify_password("x", bad) is False
