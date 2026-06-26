"""FL DOR land-use code → text lookup (audit fix E4)."""

from __future__ import annotations

from preprocess.normalizers.fdor_use_codes import DOR_USE_CODES, land_use_desc


def test_known_codes_decode_to_documented_text():
    # The anchors the FL parcel dossier names explicitly.
    assert land_use_desc("000") == "Vacant residential"
    assert land_use_desc("001") == "Single family"
    assert land_use_desc("004") == "Condominium"
    assert land_use_desc("071") == "Churches"
    assert land_use_desc("072") == "Private schools and colleges"
    assert land_use_desc("094") == "Rights-of-way, streets, roads, ditches"


def test_tolerates_the_raw_shapes_the_code_arrives_in():
    # "001" / "01" / "1" / 1 / 1.0 all mean code 1.
    assert land_use_desc("01") == "Single family"
    assert land_use_desc("1") == "Single family"
    assert land_use_desc(1) == "Single family"
    assert land_use_desc(1.0) == "Single family"


def test_unknown_blank_and_local_codes_return_none():
    assert land_use_desc("") is None
    assert land_use_desc(None) is None
    assert land_use_desc("  ") is None
    assert land_use_desc("not a code") is None
    assert land_use_desc("150") is None  # local code ≥ 100 → no statewide text


def test_table_covers_the_full_documented_0_99_range():
    assert set(DOR_USE_CODES) == set(range(100))
    assert all(isinstance(v, str) and v for v in DOR_USE_CODES.values())
