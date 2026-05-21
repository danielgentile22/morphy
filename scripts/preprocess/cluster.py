"""Owner clustering helpers.

We group parcels by (normalized owner name + normalized mailing address)
to detect multi-parcel owners. This is the foundation for portfolio
outreach features and for owner-unmasking (combining with FCC ULS
ownership data later).

Conservative by default: two parcels join only if both the normalized
name AND the normalized mailing address match exactly. Address-only or
name-only matches would create false positives (different people with
the same address; same person with multiple business addresses).
"""

from __future__ import annotations

import hashlib
import re

import pandas as pd

# Words that don't help disambiguate owners.
_NOISE_WORDS = re.compile(
    r"\b(LLC|L\.L\.C\.|INC|INC\.|CORP|CORP\.|CO|CO\.|LTD|LTD\.|TRUST|"
    r"TRUSTEE|TRUSTEES|FAMILY|REVOCABLE|LIVING|ETAL|ET AL|JR|SR|II|III|IV)\b",
    re.IGNORECASE,
)
_PUNCT = re.compile(r"[^\w\s]")
_MULTI_WS = re.compile(r"\s+")

# U.S.-federal-government name aliases. All collapse to one owner-cluster
# key and classify as `gov`. Matched (with fullmatch) against an
# upper-cased, punctuation-stripped, whitespace-collapsed name — so it
# catches "USA", "US", "U S", "U S A", "U.S.A.", the repeated "US US"
# data-entry form, and the spelled-out forms.
_US_GOV_ALIAS = re.compile(r"(?:U\s*S\s*A?\s*)+|UNITED STATES(?:\s+OF\s+AMERICA)?")


def normalize_owner_name(name) -> str:
    """Uppercased, punctuation-stripped, sorted-tokens variant of an owner name.

    Sorting tokens makes 'SMITH JOHN A' and 'JOHN A SMITH' compare equal.
    Stripping suffix/entity noise makes 'SMITH FAMILY TRUST' compare equal to
    'SMITH FAMILY' (debatable; we lean toward more clustering).
    """
    if name is None or (isinstance(name, float) and pd.isna(name)):
        return ""
    s = str(name).upper()
    s = _PUNCT.sub(" ", s)
    s = _NOISE_WORDS.sub(" ", s)
    s = _MULTI_WS.sub(" ", s).strip()
    if not s:
        return ""
    # Collapse U.S.-government name variants to one canonical key so
    # federal land doesn't fragment into "USA" / "U S" / "U S A" clusters.
    if _US_GOV_ALIAS.fullmatch(s):
        return "UNITED STATES"
    tokens = sorted(s.split())
    return " ".join(tokens)


def normalize_address(addr) -> str:
    """Uppercased, punctuation-stripped, abbreviation-collapsed mailing address."""
    if addr is None or (isinstance(addr, float) and pd.isna(addr)):
        return ""
    s = str(addr).upper()
    s = _PUNCT.sub(" ", s)
    s = _MULTI_WS.sub(" ", s).strip()
    # Common street-suffix collapses
    for full, short in (
        ("STREET", "ST"),
        ("ROAD", "RD"),
        ("AVENUE", "AVE"),
        ("DRIVE", "DR"),
        ("LANE", "LN"),
        ("BOULEVARD", "BLVD"),
        ("HIGHWAY", "HWY"),
        ("COURT", "CT"),
        ("PARKWAY", "PKWY"),
        ("CIRCLE", "CIR"),
        ("PLACE", "PL"),
        ("TERRACE", "TER"),
    ):
        s = re.sub(rf"\b{full}\b", short, s)
    return s


def cluster_id(owner_norm: str, addr_norm: str) -> str:
    """Deterministic short ID for a (normalized name, normalized address) pair.

    Returns empty string if both are empty (un-clusterable).
    """
    if not owner_norm and not addr_norm:
        return ""
    key = f"{owner_norm}|{addr_norm}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


# Unambiguous government / public-entity markers. Matched against the
# punctuation-normalised name (dots/punctuation -> spaces) so abbreviated
# forms like "ARK. HWY. DEPT." and "U.S. DEPT. OF AGRICULTURE" are caught.
# Checked *before* the LLC/trust/corp patterns so a government name that
# happens to contain "TRUST" or "CORP" ("STATE OF MONTANA - TRUST",
# "ARMY CORP OF ENGINEERS") still classifies as gov rather than trust/corp.
_GOV_STRONG = re.compile(
    r"\bUSDA\b|\bUSDI\b|\bU S D [AI]\b|\bBIA\b|\bBLM\b|"
    r"\bBUREAU OF\b|\bFOREST SERVICE\b|\bNATIONAL FOREST\b|\bNATIONAL PARK\b|"
    r"\bFISH\s+(?:AND\s+)?(?:WILDLIFE|GAME)\b|"
    r"\bARMY CORPS?\b|\bCORPS? OF ENGINEERS\b|\bPOSTAL SERVICE\b|"
    r"\bDEPARTMENT OF\b|\bDEPT OF\b|\bSECRETARY OF\b|"
    r"\bSTATE OF\b|\bCITY OF\b|\bCOUNTY OF\b|"
    r"\bSTATE HIGHWAY\b|\bSTATE HWY\b|\bHIGHWAY COMM|\bHWY COMM|"
    r"\bHIGHWAY DEPT|\bHWY DEPT|\bHIWAY\b|"
    r"\bHOUSING AUTHORITY\b|\bAIRPORT AUTHORITY\b|\bPORT AUTHORITY\b|"
    r"\bDNRC\b|\bSCHOOL TRUST\b|\bGRAZING DIST|\bIRRIGATION DIST|"
    r"\bIN TRUST\b|\bRESERVATION\b|\bINDIAN COMMUNITY\b|\bINDIAN TRIBE\b|"
    r"\bTRIBES?\b|\bTRIBAL\b|"
    r"\bCOUNTY(?:[, ]+(?:ARKANSAS|MONTANA))?\s*$|"
    # Montana's two consolidated city-county governments carry no generic
    # keyword, so they are named explicitly.
    r"\bBUTTE SILVER BOW\b|\bANACONDA DEER LODGE\b",
    re.IGNORECASE,
)

# Entity-type patterns, checked in order against the raw name. Government
# is handled separately by _GOV_STRONG (above) and this weak fallback,
# whose tokens (USA, GOVERNMENT) also turn up inside private business
# names — so it runs *after* LLC/trust/corp/partnership.
_OWNER_KIND_PATTERNS = [
    ("llc", re.compile(r"\bLLC\b|\bL\.?L\.?C\.?\b", re.IGNORECASE)),
    ("trust", re.compile(r"\bTRUST\b|\bTRUSTEES?\b", re.IGNORECASE)),
    (
        "corporation",
        re.compile(r"\bCORP\b|\bINC\b|\bCORPORATION\b|\bINCORPORATED\b", re.IGNORECASE),
    ),
    ("partnership", re.compile(r"\bLP\b|\bLLP\b|\bPARTNERSHIP\b|\bL\.?P\.?\b", re.IGNORECASE)),
    (
        "gov",
        re.compile(
            r"\bUNITED STATES\b|\bUSA\b|\bGOVERNMENT\b|\bMUNICIPAL\b|"
            r"\bTOWNSHIP\b|\bVILLAGE OF\b",
            re.IGNORECASE,
        ),
    ),
    ("church", re.compile(r"\bCHURCH\b|\bMINISTRIES\b|\bPARISH\b", re.IGNORECASE)),
    ("school", re.compile(r"\bSCHOOLS?\b|\bUNIVERSITY\b|\bCOLLEGE\b|\bACADEMY\b", re.IGNORECASE)),
]


def _looks_like_person(part: str) -> bool:
    """True if a name fragment is a short run of alphabetic name tokens.

    Allows ``.`` and ``-`` inside a token (initials, hyphenated surnames).
    """
    toks = part.split()
    if not (1 <= len(toks) <= 4):
        return False
    return all(t.replace(".", "").replace("-", "").isalpha() for t in toks)


def infer_owner_kind(name) -> str:
    """Tag an owner name as one of:
    'llc', 'trust', 'corporation', 'partnership', 'gov', 'church', 'school',
    'individual', 'unknown'.
    """
    if name is None or (isinstance(name, float) and pd.isna(name)):
        return "unknown"
    s = str(name)
    if not s.strip():
        return "unknown"
    # Government detection runs first, against a punctuation-normalised
    # form: bare U.S.-government aliases ("USA", "U S A"), then the strong
    # government markers. Doing this before the entity loop means a
    # government name containing "TRUST"/"CORP" is not mis-tagged.
    cleaned = _MULTI_WS.sub(" ", _PUNCT.sub(" ", s.upper())).strip()
    if _US_GOV_ALIAS.fullmatch(cleaned):
        return "gov"
    if _GOV_STRONG.search(cleaned):
        return "gov"
    for kind, pat in _OWNER_KIND_PATTERNS:
        if pat.search(s):
            return kind
    # Heuristic 1: clean ALL-CAPS space-separated names are individuals
    # (NC OneMap-style 'SMITH JOHN A' or 'JONES MARY ANN').
    tokens = s.upper().split()
    if 2 <= len(tokens) <= 5 and all(t.replace(".", "").isalpha() for t in tokens):
        return "individual"
    # Heuristic 2: joint / comma-formatted individual names. County
    # assessor data records owners as 'SMITH, JOHN & MARY',
    # 'JONES JOHN/JANE', 'DOE JANE ET UX'. Strip the marital/heir tags,
    # split on the joint-owner separators, and require every resulting
    # fragment to look like a short person-name token run. This is the
    # bulk of the AR 'unknown' rate (commas + ampersands).
    u = re.sub(r"\bET\s*UX\b|\bET\s*AL\b|\bET\s*VIR\b", " ", s.upper())
    parts = [p for p in re.split(r"[&/;,]| AND ", u) if p.split()]
    if parts and all(_looks_like_person(p) for p in parts):
        return "individual"
    return "unknown"
