"""Tests for the HTTP Range parser in scripts/serve.py.

`_parse_byte_range` is the load-bearing piece of the range-capable
static server. PMTiles + DuckDB-WASM rely on correct Range/206 responses;
a parser bug here would surface as silent fetch failures in the map app.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from serve import _parse_byte_range  # noqa: E402


SIZE = 1000


def test_explicit_range() -> None:
    assert _parse_byte_range("bytes=0-99", SIZE) == (0, 99)


def test_open_ended_range_clamps_to_size_minus_one() -> None:
    assert _parse_byte_range("bytes=500-", SIZE) == (500, SIZE - 1)


def test_suffix_range_returns_final_n_bytes() -> None:
    assert _parse_byte_range("bytes=-100", SIZE) == (SIZE - 100, SIZE - 1)


def test_suffix_range_larger_than_size_starts_at_zero() -> None:
    assert _parse_byte_range("bytes=-99999", SIZE) == (0, SIZE - 1)


def test_explicit_end_clamped_to_size_minus_one() -> None:
    assert _parse_byte_range("bytes=0-99999", SIZE) == (0, SIZE - 1)


def test_first_range_is_taken_when_multiple_specified() -> None:
    assert _parse_byte_range("bytes=0-99, 200-299", SIZE) == (0, 99)


def test_rejects_non_bytes_unit() -> None:
    with pytest.raises(ValueError, match="unsupported range unit"):
        _parse_byte_range("words=0-99", SIZE)


def test_rejects_malformed_missing_dash() -> None:
    with pytest.raises(ValueError, match="malformed range"):
        _parse_byte_range("bytes=100", SIZE)


def test_rejects_zero_or_negative_suffix() -> None:
    with pytest.raises(ValueError, match="malformed suffix range"):
        _parse_byte_range("bytes=-0", SIZE)


def test_rejects_unsatisfiable_start_past_size() -> None:
    with pytest.raises(ValueError, match="unsatisfiable range"):
        _parse_byte_range("bytes=2000-3000", SIZE)


def test_rejects_unsatisfiable_when_start_gt_end() -> None:
    with pytest.raises(ValueError, match="unsatisfiable range"):
        _parse_byte_range("bytes=500-100", SIZE)
