"""FAA DOF rows must not write into ``asr_number`` (audit M-i / #215).

The FAA obstacle number is a disjoint namespace from FCC ASR registration
numbers; before the split it rode the same ``asr_number`` column and made
the mixed towers layer FAA-noisy as a global key. Pin the normalizer-level
contract: ``asr_number`` is null on FAA rows, the obstacle number lives in
``obstacle_number``, and ``_source_row_id`` (the union-wide identity every
consumer keys on) still carries it.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
from preprocess.normalizers.faa_oeaaa import _FW_FIELDS, FaaDofNormalizer


def _dof_line(values: dict[str, str]) -> str:
    """Build one fixed-width DOF.DAT line from field → value."""
    width = max(end for _, _, end in _FW_FIELDS)
    chars = [" "] * max(width, 100)  # parser skips lines under 100 chars
    for name, start, end in _FW_FIELDS:
        v = values.get(name, "")
        for i, ch in enumerate(v[: end - start + 1]):
            chars[start - 1 + i] = ch
    return "".join(chars)


def _write_fixture(raw_dir: Path) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "HEADER - skipped (obstacle number not numeric)".ljust(120),
        _dof_line(
            {
                "oas_code": "05",
                "obstacle_number": "123456",
                "verification_status": "O",
                "country": "US",
                "state": "AR",
                "city": "LITTLE ROCK",
                "lat_dms": "34-44-46.00N",
                "lon_dms": "092-17-21.00W",
                "obstacle_type": "TOWER",
                "quantity": "1",
                "agl_ft": "0150",
                "amsl_ft": "0500",
            }
        ),
    ]
    (raw_dir / "DOF.DAT").write_text("\n".join(lines), encoding="latin-1")


def test_faa_rows_keep_asr_number_null_and_carry_obstacle_number(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    out = tmp_path / "out"
    _write_fixture(raw)

    result = FaaDofNormalizer().normalize(raw, out)
    assert result.canonical_rows == 1

    towers = gpd.read_parquet(out / "towers.parquet")
    row = towers.iloc[0]
    assert row["asr_number"] is None or str(row["asr_number"]) in ("", "None", "nan")
    assert row["obstacle_number"] == "123456"
    # The union-wide identity consumers key on is unchanged.
    assert row["_source_row_id"] == "123456"
    # Sanity: the fixed-width parse itself worked (coords + type land).
    assert row["structure_type"] == "TOWER"
    assert abs(row["lat"] - 34.746) < 0.01
    assert abs(row["lon"] - -92.289) < 0.01
