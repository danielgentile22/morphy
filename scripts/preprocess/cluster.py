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
        ("STREET", "ST"), ("ROAD", "RD"), ("AVENUE", "AVE"), ("DRIVE", "DR"),
        ("LANE", "LN"), ("BOULEVARD", "BLVD"), ("HIGHWAY", "HWY"),
        ("COURT", "CT"), ("PARKWAY", "PKWY"), ("CIRCLE", "CIR"),
        ("PLACE", "PL"), ("TERRACE", "TER"),
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


_OWNER_KIND_PATTERNS = [
    ("llc", re.compile(r"\bLLC\b|\bL\.?L\.?C\.?\b", re.IGNORECASE)),
    ("trust", re.compile(r"\bTRUST\b|\bTRUSTEES?\b", re.IGNORECASE)),
    ("corporation", re.compile(r"\bCORP\b|\bINC\b|\bCORPORATION\b|\bINCORPORATED\b", re.IGNORECASE)),
    ("partnership", re.compile(r"\bLP\b|\bLLP\b|\bPARTNERSHIP\b|\bL\.?P\.?\b", re.IGNORECASE)),
    ("gov", re.compile(
        r"\bUNITED STATES\b|\bUSA\b|\bSTATE OF\b|\bCITY OF\b|\bCOUNTY OF\b|"
        r"\bMUNICIPAL\b|\bTOWNSHIP\b|\bVILLAGE OF\b|\bGOVERNMENT\b|"
        r"\bUS FOREST SERVICE\b|\bBIA\b|\bBLM\b|\bDEPT\b OF",
        re.IGNORECASE,
    )),
    ("church", re.compile(r"\bCHURCH\b|\bMINISTRIES\b|\bPARISH\b", re.IGNORECASE)),
    ("school", re.compile(r"\bSCHOOL\b|\bUNIVERSITY\b|\bCOLLEGE\b|\bACADEMY\b", re.IGNORECASE)),
]


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
    for kind, pat in _OWNER_KIND_PATTERNS:
        if pat.search(s):
            return kind
    # Heuristic: ALL CAPS LAST-FIRST patterns are individuals
    # (NC OneMap-style 'SMITH JOHN A' or 'JONES MARY ANN')
    tokens = s.upper().split()
    if 2 <= len(tokens) <= 5 and all(t.replace(".", "").isalpha() for t in tokens):
        return "individual"
    return "unknown"
