"""infer_owner_kind — the expanded owner-type classifier (MACRO-7 / #222, ADR-076).

A hand-labeled sample doubles as the regression fixture AND the accuracy eval the
ADR asks for. No real parcel-owner names (TESTING.md §4) — these are synthetic
representatives of each taxonomy class. The `towerco`/`utility`/`nonprofit`
classes are the new ones the audit found the old suffix-only regex missed.
"""

from __future__ import annotations

from preprocess.cluster import infer_owner_kind

# (name, expected_kind). Cases marked "# new" are ones the pre-#222 regex tagged
# wrong (llc/corporation/unknown) — the expanded classifier gets them right.
LABELED_SAMPLE: list[tuple[str, str]] = [
    ("CROWN CASTLE TOWERS LLC", "towerco"),  # new — was llc
    ("AMERICAN TOWER CORPORATION", "towerco"),  # new — was corporation
    ("SBA COMMUNICATIONS CORP", "towerco"),  # new — was corporation
    ("VERTICAL BRIDGE HOLDINGS LLC", "towerco"),  # new — was llc
    ("XCEL ENERGY INC", "utility"),  # new — was corporation
    ("OZARK ELECTRIC COOPERATIVE", "utility"),  # new — was unknown
    ("MONTANA POWER COMPANY", "utility"),  # new — was unknown
    ("FIRST ELECTRIC COOP", "utility"),  # new — was unknown
    ("NATURE CONSERVANCY", "nonprofit"),  # new — was unknown
    ("THE SMITH FOUNDATION", "nonprofit"),  # new — was unknown
    ("ACME PROPERTIES LLC", "llc"),
    ("SMITH FAMILY TRUST", "trust"),
    ("WIDGET INDUSTRIES INC", "corporation"),
    ("RIVERSIDE HOLDINGS LP", "partnership"),
    ("CITY OF DALLAS", "gov"),
    ("STATE OF MONTANA", "gov"),
    ("UNITED STATES OF AMERICA", "gov"),
    ("FIRST BAPTIST CHURCH", "church"),
    ("MOUNTAIN VIEW ACADEMY", "school"),
    ("SMITH JOHN", "individual"),
    ("DOE JANE & JOHN", "individual"),
    ("LOT 5 BLOCK 2", "unknown"),
]


def test_labeled_sample_classifies_100_percent():
    """Every labeled representative classifies to its expected kind — the
    regression fixture. A drop here means the regex regressed."""
    wrong = [
        (n, exp, infer_owner_kind(n)) for n, exp in LABELED_SAMPLE if infer_owner_kind(n) != exp
    ]
    assert not wrong, f"misclassified: {wrong}"


def test_towerco_and_utility_beat_the_generic_legal_suffix():
    """A named tower company / utility that ALSO carries LLC/INC must tag as the
    specific kind, not the generic suffix — this is the ordering fix."""
    assert infer_owner_kind("CROWN CASTLE LLC") == "towerco"
    assert infer_owner_kind("SBA MONARCH TOWERS LLC") == "towerco"
    assert infer_owner_kind("XCEL ENERGY INC") == "utility"
    assert infer_owner_kind("OZARK ELECTRIC COOPERATIVE INC") == "utility"


def test_gov_still_wins_over_a_contained_entity_keyword():
    """A government name containing TRUST/CORP is still gov (runs first)."""
    assert infer_owner_kind("STATE OF ARKANSAS SCHOOL TRUST") == "gov"
