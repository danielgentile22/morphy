"""Carrier-brand rollup: raw ULS legal-entity string → consumer carrier brand.

Slice A (#22). A ULS spectrum license is held by a *legal entity* whose name
has hundreds of variants ("New Cingular Wireless PCS, LLC", "AT&T Mobility
Spectrum, LLC", "Cellco Partnership", "Sprint Spectrum LP"). The co-founder
wants the **parent consumer brand** on a tower — AT&T / Verizon / T-Mobile /
Dish / … — not the raw entity string. This module is the pure mapping that does
that bucketing, and *only* that.

**Vocabulary (GLOSSARY.md).** A CARRIER is the ULS spectrum LICENSEE operating on
a tower (this module). It is NOT the VENDOR / REGISTRANT — the tower-co that owns
the structure (Crown Castle, American Tower, …), which comes from FCC ASR and is
Slice B. Do not conflate them.

**What this is NOT.** Name-pattern bucketing of public legal-entity strings into
public consumer brands using a hand-maintained table of documented corporate
lineage. It is explicitly NOT skip-trace and NOT LLC unmasking (ADR-041, as
narrowed by ADR-057): no external lookups, no human-identity resolution, no
network. Pure, deterministic, stdlib-only.

The string we map is the LICENSEE name (EN ``entity_type == 'L'`` /
``license.licensee_name`` from the #12 normalizer). ``callsign`` is accepted in
the signature (the #24 ULS↔ASR join calls per-license) but is currently a
reserved tertiary disambiguator — the entity name is the authoritative signal.

----------------------------------------------------------------------------
HOW THE MAPPING WORKS
----------------------------------------------------------------------------
1. ``_normalize`` upper-cases the entity name and collapses every run of
   non-alphanumeric characters to a single space, so "AT&T Mobility, L.L.C."
   and "AT&T MOBILITY LLC" both become "AT T MOBILITY LLC". Patterns are written
   against this spaced-uppercase form.
2. :data:`CARRIER_PATTERNS` is an ORDERED list of ``(regex, brand)`` rows. The
   normalized name is tested top-to-bottom and the **first** regex to match
   wins (most-specific first). The brand tokens are designed to be mutually
   exclusive across brands, so ordering only ever chooses the most-specific
   *variant*, never which brand — but the first-match rule is what makes the
   result deterministic.
3. No match → the entity is in the **tail**: return the raw entity name with
   ``is_mapped=False`` so the surface still shows *something* truthful.

----------------------------------------------------------------------------
ADD-A-CARRIER WORKFLOW  (issue #22 acceptance criterion)
----------------------------------------------------------------------------
To add or extend a brand:

1. Add a ``(r"PATTERN", "Brand Name")`` row to :data:`CARRIER_PATTERNS`. Write
   the pattern against the *normalized* form (see step 1 above): upper-case,
   punctuation already turned into single spaces, so "T-Mobile" is ``T MOBILE``
   and "L.L.C." is ``L L C``. Use ``\b`` boundaries for short/ambiguous tokens
   (``\bUSCC\b``) and bare substrings for distinctive ones (``CELLCO``).
2. Place a more-specific pattern ABOVE a broader one that could also match it
   (first-match-wins). Patterns for *different* brands must stay mutually
   exclusive — if a new token could match an existing brand's strings, tighten
   it. Only map a legal entity to a brand when the corporate lineage is
   *documented and unambiguous* (see the ALLTEL note below for the counter-case).
3. Add the new variant(s) to ``tests/test_carrier_brands.py`` (a real ULS string
   → expected brand) so the mapping is pinned.
4. Re-run the coverage check to see the effect on mapped-share and the new tail:
       source .venv/bin/activate
       python scripts/audits/carrier_brand_coverage.py
   That audit is a one-off (NOT part of the pipeline); it reads the #12
   normalized ``entity`` parquet and reports mapped-share + the top unmapped
   entities — i.e. the next candidates to add.

Deliberately-UNMAPPED legacy holders: some entities are genuinely ambiguous and
are left in the tail ON PURPOSE rather than guessed — e.g. "ALLTEL Corporation",
whose licenses were split between Verizon (the bulk, 2009) and AT&T (a divested
subset), and bare "<City> SMSA/RSA Limited Partnership" cellular partnerships
that were sold market-by-market. Showing the raw name (``is_mapped=False``) is
more honest than picking a brand we can't defend.
"""

from __future__ import annotations

import math
import re

# Canonical brand labels. Downstream surfaces display these verbatim.
ATT = "AT&T"
VERIZON = "Verizon"
TMOBILE = "T-Mobile"
DISH = "Dish"
US_CELLULAR = "US Cellular"
C_SPIRE = "C-Spire"
CAROLINA_WEST = "Carolina West Wireless"
PINE_BELT = "Pine Belt"
BLUEGRASS = "Bluegrass Cellular"

#: The set of canonical brands this module can emit (for downstream validation).
CARRIERS: frozenset[str] = frozenset(
    {ATT, VERIZON, TMOBILE, DISH, US_CELLULAR, C_SPIRE, CAROLINA_WEST, PINE_BELT, BLUEGRASS}
)

# Ordered (pattern, brand) table, scanned top-to-bottom; first match wins.
# Patterns match the NORMALIZED name (upper-case, punctuation → single space).
# Grouped by brand for readability; the why-this-is-here notes are inline only
# where the lineage isn't obvious.
CARRIER_PATTERNS: list[tuple[str, str]] = [
    # ── AT&T ── Cingular (2004 buy of AT&T Wireless) → renamed AT&T (2007);
    # BellSouth/Southwestern Bell/Ameritech/PacBell were the SBC-side predecessors;
    # Cricket/Leap is AT&T's prepaid brand (2014).
    (r"NEW CINGULAR", ATT),
    (r"\bCINGULAR\b", ATT),
    (r"AT T MOBILITY", ATT),
    (r"AT T WIRELESS", ATT),
    (r"\bBELLSOUTH\b", ATT),
    (r"SOUTHWESTERN BELL", ATT),
    (r"PACIFIC BELL WIRELESS", ATT),
    (r"AMERITECH (MOBILE|CELLULAR)", ATT),
    (r"\bCRICKET\b", ATT),
    (r"LEAP WIRELESS", ATT),
    # ── Verizon ── Cellco Partnership d/b/a Verizon Wireless; Bell Atlantic
    # Mobile + AirTouch + GTE Wireless (2000) were the founding entities.
    (r"\bCELLCO\b", VERIZON),
    (r"\bVERIZON\b", VERIZON),
    (r"BELL ATLANTIC", VERIZON),
    (r"\bAIRTOUCH\b", VERIZON),
    (r"GTE (MOBILNET|WIRELESS)", VERIZON),
    (r"RURAL CELLULAR CORPORATION", VERIZON),  # RCC / "Unicel", wholly acquired by Verizon 2008
    # ── T-Mobile ── VoiceStream/Omnipoint/Powertel (2001) became T-Mobile USA;
    # MetroPCS (2013), Sprint+Nextel+Clearwire (2020), iWireless (2018) all rolled in.
    (r"\bT MOBILE\b", TMOBILE),
    (r"METRO ?PCS|METROPCS|METRO BY T MOBILE", TMOBILE),
    (r"\bVOICESTREAM\b", TMOBILE),
    (r"\bOMNIPOINT\b", TMOBILE),
    (r"\bPOWERTEL\b", TMOBILE),
    (r"\bSPRINT", TMOBILE),  # Sprint Spectrum / SprintCom / Sprint PCS / Sprint Nextel
    (r"\bNEXTEL\b", TMOBILE),
    (r"\bCLEARWIRE\b", TMOBILE),
    (r"IOWA WIRELESS|IWIRELESS", TMOBILE),
    # ── Dish ── DISH Network / Echostar (re-merged 2023) + Boost (divested to
    # Dish in the 2020 T-Mobile/Sprint merger). The block below maps Dish's
    # documented spectrum subsidiaries + AWS-3 designated entities (Northstar /
    # SNR — FCC-found de-facto Dish control) — public-record lineage, not unmasking.
    (r"\bDISH\b", DISH),
    (r"\bECHOSTAR\b", DISH),
    (r"\bBOOST\b", DISH),
    (r"NORTHSTAR WIRELESS", DISH),
    (r"SNR WIRELESS", DISH),
    (r"AMERICAN H BLOCK", DISH),
    (r"GAMMA ACQUISITION", DISH),
    (r"MANIFEST WIRELESS", DISH),
    (r"\bDBSD\b", DISH),
    # ── US Cellular ── USCC = US Cellular Corp; USCOC = US Cellular Operating Co.
    (r"UNITED STATES CELLULAR", US_CELLULAR),
    (r"\bUS CELLULAR\b", US_CELLULAR),
    (r"\bUSCC\b", US_CELLULAR),
    (r"\bUSCOC\b", US_CELLULAR),
    # ── C-Spire ── Cellular South rebranded to C-Spire (2011); Telapex is parent.
    (r"\bC SPIRE\b|\bCSPIRE\b", C_SPIRE),
    (r"CELLULAR SOUTH", C_SPIRE),
    (r"\bTELAPEX\b", C_SPIRE),
    # ── Named regional brands (issue top-N) ──
    (r"CAROLINA WEST", CAROLINA_WEST),
    (r"PINE BELT", PINE_BELT),
    # "Bluegrass" alone is a pervasive Kentucky place-name; require a wireless
    # qualifier so unrelated entities (e.g. "Bluegrass Water Utility") stay in
    # the tail rather than getting a false carrier attribution.
    (r"BLUEGRASS (CELLULAR|WIRELESS)\b", BLUEGRASS),
]

# Compiled once at import. Pattern strings already target the upper-case
# normalized form, so no IGNORECASE flag is needed.
_COMPILED: list[tuple[re.Pattern[str], str]] = [
    (re.compile(p), brand) for p, brand in CARRIER_PATTERNS
]


def _raw_name(value) -> str | None:
    """The entity string as-displayed: trimmed, or None for blank/missing.

    NaN is detected without pandas (stdlib-only contract): a float NaN is the
    only value not equal to itself.
    """
    if value is None:
        return None
    if isinstance(value, float):
        if math.isnan(value):
            return None
        value = repr(value)  # numeric name is nonsense but must not crash
    s = str(value).strip()
    return s or None


def _normalize(value) -> str:
    """Upper-case + collapse every non-alphanumeric run to a single space.

    "AT&T Mobility, L.L.C." → "AT T MOBILITY L L C". Returns "" for blank/None.
    """
    s = _raw_name(value)
    if s is None:
        return ""
    return re.sub(r"[^A-Z0-9]+", " ", s.upper()).strip()


def carrier_for(callsign, entity_name) -> tuple[str | None, bool]:
    """Map a ULS licensee to a consumer carrier brand.

    Args:
        callsign: the license call sign. Reserved tertiary disambiguator —
            currently unused; the entity name is the authoritative signal.
        entity_name: the raw ULS licensee legal-entity string (EN entity_type
            'L' / ``license.licensee_name``).

    Returns:
        ``(carrier_name, is_mapped)``:
          * matched   → ``(canonical_brand, True)``
          * tail      → ``(raw_entity_name, False)`` — show the real string
          * blank/None→ ``(None, False)``

    Never raises (mirrors the fips.py robustness contract): a normalizer feeding
    null/garbage entity names gets a clean tail row, not an exception.
    """
    name = _normalize(entity_name)
    if not name:
        return None, False
    for pattern, brand in _COMPILED:
        if pattern.search(name):
            return brand, True
    return _raw_name(entity_name), False
