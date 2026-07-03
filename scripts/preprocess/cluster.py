"""Owner identity — the single home for the normalize → hash recipe.

This module owns *all* owner-key derivation so callers never re-derive it:

- ``normalize_owner_name`` / ``normalize_address`` — the normalization recipe.
- ``normalized_owner_cols`` — the "prefer the precomputed ``*_norm`` column,
  else re-normalize the raw column" fallback every parcel-frame consumer used
  to repeat.
- Two named hash grains, chosen explicitly rather than ad hoc:
    * ``cluster_id(name_norm, addr_norm)`` — **within-state**: name *and*
      mailing address. Conservative — two parcels join only if both match, so
      different people who share a name don't merge (ADR-024).
    * ``cross_state_owner_key(name_norm, state_fips)`` — **cross-state**:
      **name + state** (ADR-075). Same-name owners in different states get
      different keys, so "CITY OF JACKSONVILLE" in AR and FL are two Leads —
      the err-toward-not-merging default. A curated multi-state alias table
      (``_MULTISTATE_ALIASES`` — towercos: Crown Castle / American Tower / SBA /
      Vertical Bridge) is the deliberate exception: a matching name keys on the
      canonical alias with **no state**, re-merging that entity's per-state
      fragments into one national Lead. The mailing address stays dropped.
      ``legacy_cross_state_owner_key(name_norm)`` reproduces the pre-ADR-075
      name-only recipe — used *only* to emit the old→new migration map.
  The two grains are intentionally different and must stay that way — do not
  add the address to the cross-state key or remove it from the within-state
  key.

``infer_owner_kind`` (owner-name → entity class) is a separate concern kept
here for proximity but is not part of the key recipe.
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


# The key's wire format: what gets hashed, how it's joined, how much survives.
# Shared by the Python recipe below and the generated SQL form, so a grain
# change edits these (and nothing in compose.py).
KEY_SEPARATOR = "|"
KEY_HEX_LEN = 12


def cluster_id(owner_norm: str, addr_norm: str) -> str:
    """Within-state owner key: SHA1 of ``name_norm + '|' + addr_norm`` (12 hex).

    The address is folded in *by design* — two parcels join only if both the
    normalized name AND address match, so different people who share a name
    don't merge (conservative; ADR-024). Contrast ``cross_state_owner_key``,
    the name-only grain. Returns empty string if both inputs are empty
    (un-clusterable).
    """
    if not owner_norm and not addr_norm:
        return ""
    key = f"{owner_norm}{KEY_SEPARATOR}{addr_norm}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:KEY_HEX_LEN]


# ── SQL forms of the recipe (PRD #135 compose pre-pass) ──────────────────────
# The DuckDB pre-pass keys rows natively for speed; the SQL text is GENERATED
# here so the recipe still has exactly one home (a UDF would put per-row
# Python back into the 11M-row hot loop). DuckDB's sha1() over UTF-8 matches
# hashlib, and trim() matches the strip-blank test because stored norms are
# whitespace-collapsed at normalize time — both pinned by the equivalence
# harness and tests/test_owner_key_sql.py.


def blank_sql(col_expr: str) -> str:
    """SQL for the blank test the prefer-precomputed-norm rule applies."""
    return f"({col_expr} IS NULL OR trim({col_expr}) = '')"


def nonblank_sql(col_expr: str) -> str:
    return f"({col_expr} IS NOT NULL AND trim({col_expr}) != '')"


def prefer_norm_sql(norm_expr: str) -> str:
    """The stored norm when non-blank, else '' — the SQL half of
    :func:`_prefer_precomputed_norm` (recoverable rows are routed to the
    Python recipe by :func:`needs_python_sql`, never re-normalized in SQL)."""
    return f"CASE WHEN NOT {blank_sql(norm_expr)} THEN {norm_expr} ELSE '' END"


def needs_python_sql(
    name_norm_expr: str, name_raw_expr: str, addr_norm_expr: str, addr_raw_expr: str
) -> str:
    """Rows the SQL path must NOT key: a blank stored norm alongside a
    non-blank raw value — those re-normalize through the live Python recipe."""
    return (
        f"(({blank_sql(name_norm_expr)} AND {nonblank_sql(name_raw_expr)}) "
        f"OR ({blank_sql(addr_norm_expr)} AND {nonblank_sql(addr_raw_expr)}))"
    )


def cluster_id_sql(name_expr: str, addr_expr: str) -> str:
    """The SQL form of :func:`cluster_id`: both-empty → '' else
    ``substr(sha1(name || '|' || addr), 1, 12)``."""
    key = f"{name_expr} || '{KEY_SEPARATOR}' || {addr_expr}"
    return (
        f"CASE WHEN {name_expr} = '' AND {addr_expr} = '' THEN '' "
        f"ELSE substr(sha1({key}), 1, {KEY_HEX_LEN}) END"
    )


# Curated multi-state entities that SHOULD merge across state lines (ADR-075) —
# the targeted exception to the state-scoped key. These are the towercos whose
# name variants would otherwise fragment one real owner into many per-state
# Leads. A hit keys on the canonical alias with NO state, collapsing every
# variant across every state to one Lead.
#
# Matched by *token subset* against the normalized name, because
# ``normalize_owner_name`` sorts tokens ("CROWN CASTLE" → "CASTLE CROWN") — so an
# ordered substring match would fail. Tokens are singular-stemmed (one trailing
# "S" dropped) so TOWER/TOWERS, STRUCTURE/STRUCTURES match either way. Public
# corporate names only — NOT unmasking (ADR-041/057). Keep it short + documented;
# add a utility/landowner here only when its multi-state fragmentation is
# confirmed in the data.
#
# Each rule: (required tokens all present) AND (one of the qualifier tokens, or
# no qualifier). ``SBA`` carries a required towerco qualifier so the Small
# Business Administration (a gov entity, no such qualifier) never matches.
_MULTISTATE_ALIASES: list[tuple[frozenset[str], frozenset[str], str]] = [
    (frozenset({"CROWN", "CASTLE"}), frozenset(), "CROWN CASTLE"),
    (frozenset({"AMERICAN", "TOWER"}), frozenset(), "AMERICAN TOWER"),
    (frozenset({"VERTICAL", "BRIDGE"}), frozenset(), "VERTICAL BRIDGE"),
    (
        frozenset({"SBA"}),
        frozenset({"COMMUNICATION", "TOWER", "NETWORK", "STRUCTURE", "MONARCH", "INFRASTRUCTURE"}),
        "SBA",
    ),
]


def _singular_tokens(owner_name_norm: str) -> frozenset[str]:
    """The name's token set, each token with a single trailing 'S' dropped so
    plural/singular company-type words match either way."""
    return frozenset(
        t[:-1] if t.endswith("S") and len(t) > 1 else t for t in owner_name_norm.split()
    )


def _multistate_alias(owner_name_norm: str) -> str | None:
    """The canonical alias for a known multi-state entity, or None. Order-
    independent (token subset), so it survives the normalizer's token sort."""
    toks = _singular_tokens(owner_name_norm)
    for required, qualifiers, alias in _MULTISTATE_ALIASES:
        if required <= toks and (not qualifiers or (qualifiers & toks)):
            return alias
    return None


def cross_state_owner_key(owner_name_norm: str, state_fips: str = "") -> str:
    """Cross-state Lead key: SHA1 of ``name_norm + '|' + state`` (12 hex), an
    alias-aware **name + state** grain (ADR-075).

    Same-name owners in different states get different keys — so "CITY OF
    JACKSONVILLE" in AR (05) and FL (12) are two Leads, not one false merge.
    The mailing address stays dropped (a national portfolio owner still
    collapses *within* a state). A name matching the curated
    ``_MULTISTATE_ALIASES`` table (towercos) keys on the canonical alias with
    **no state**, deliberately re-merging its per-state fragments into one
    national Lead. Deterministic (no randomness), so a landowner keeps the same
    key every rebuild. Empty for a blank name.
    """
    if not owner_name_norm:
        return ""
    alias = _multistate_alias(owner_name_norm)
    key_input = alias if alias is not None else f"{owner_name_norm}|{state_fips}"
    return hashlib.sha1(key_input.encode("utf-8")).hexdigest()[:12]


def cross_state_owner_keys(name_norm: pd.Series, state_fips: pd.Series) -> pd.Series:
    """Vectorized :func:`cross_state_owner_key` over two aligned Series — the
    owners-index build path (millions of parcel rows). ``state_fips`` is
    zero-padded to 2 chars so "5" and "05" key identically. Blank name → blank
    key (un-clusterable)."""
    names = name_norm.astype("string").fillna("").str.strip()
    states = state_fips.astype("string").fillna("").str.strip().str.zfill(2)
    alias = names.map(_multistate_alias)
    key_input = alias.where(alias.notna(), names.str.cat(states, sep="|"))
    keyed = key_input.map(lambda s: hashlib.sha1(s.encode("utf-8")).hexdigest()[:12])
    return keyed.where(names != "", "").astype("string")


def legacy_cross_state_owner_key(owner_name_norm: str) -> str:
    """The **pre-ADR-075** cross-state key: SHA1 of the normalized name only
    (12 hex). Used *only* to emit the old→new migration map that repoints
    existing tenant lead state + merge overrides when the recipe changes — the
    live index never uses it. Deterministic; empty for a blank name."""
    if not owner_name_norm:
        return ""
    return hashlib.sha1(owner_name_norm.encode("utf-8")).hexdigest()[:12]


def _prefer_precomputed_norm(df: pd.DataFrame, norm_col: str, raw_col: str, normalize) -> pd.Series:
    """One normalized-identity column, preferring a precomputed ``*_norm``
    column and re-normalizing the raw column only where it's absent or blank.

    The single home for the "column-else-map" dance the Composer consumers
    used to each repeat: a frame that already carries the pipeline's
    precomputed column uses it verbatim (keeps the key identical to the
    analytical layers); a raw frame, or any individual row missing the
    precomputed value, falls back to ``normalize`` on the raw column. Returns
    a ``string``-dtype Series aligned to ``df.index`` — empty string where
    neither column is available (so a malformed frame degrades, never crashes).
    """
    if norm_col in df.columns:
        s = df[norm_col].astype("string").fillna("")
        blank = s.str.strip() == ""
        if blank.any() and raw_col in df.columns:
            s = s.mask(blank, df.loc[blank, raw_col].map(normalize))
        return s.astype("string").fillna("")
    if raw_col in df.columns:
        return df[raw_col].map(normalize).astype("string").fillna("")
    return pd.Series([""] * len(df), index=df.index, dtype="string")


def normalized_owner_cols(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """``(owner_name_norm, mailing_addr_norm)`` for a parcel frame.

    Prefers the pipeline's precomputed ``owner_name_norm`` / ``mailing_addr_norm``
    columns, falling back to ``normalize_owner_name`` / ``normalize_address`` on
    the raw ``owner_name`` / ``mailing_addr`` columns. The single place the
    column-fallback recipe lives: every owner-key consumer (the owner-cluster
    pre-pass, the per-chunk join, the registered join, the cross-state
    resolver) asks here instead of re-deriving it. The *producer* — the
    normalizer's ``_map_unique`` per-distinct-value path — stays where it is.
    """
    return (
        _prefer_precomputed_norm(df, "owner_name_norm", "owner_name", normalize_owner_name),
        _prefer_precomputed_norm(df, "mailing_addr_norm", "mailing_addr", normalize_address),
    )


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
# MACRO-7 (#222, ADR-076) — expanded classifier. Order matters (first match
# wins): a named tower company or a utility usually *also* carries LLC/CORP, so
# the more specific tag must run before the generic legal-suffix ones.
_OWNER_KIND_PATTERNS = [
    (
        "towerco",
        re.compile(
            r"\bAMERICAN TOWER\b|\bCROWN CASTLE\b|"
            r"\bSBA (?:COMMUNICATIONS|TOWERS|NETWORK|MONARCH|STRUCTURES)\b|"
            r"\bVERTICAL BRIDGE\b|\bGLOBAL SIGNAL\b|\bTOWERCO\b|\bTOWER CO\b|"
            r"\bTILLMAN INFRASTRUCTURE\b|\bINSITE (?:TOWER|WIRELESS)\b|"
            r"\bDIAMOND COMMUNICATIONS\b|\bTARPON TOWERS\b",
            re.IGNORECASE,
        ),
    ),
    (
        "utility",
        re.compile(
            r"\bELECTRIC (?:CO\b|COOP|COMPANY|MEMBERSHIP|POWER|UTILITY|ASSN|ASSOCIATION)|"
            r"\bPOWER (?:&|AND) LIGHT\b|\bPOWER COMPANY\b|\b(?:ELECTRIC|GAS) COOPERATIVE\b|"
            r"\bRURAL ELECTRIC\b|\bELECTRIC MEMBERSHIP\b|\bUTILITIES?\b|\bENERGY\b|"
            r"\bGAS (?:CO\b|COMPANY)|\bWATER (?:DISTRICT|AUTHORITY|WORKS|CO\b|COMPANY)|\bEMC\b",
            re.IGNORECASE,
        ),
    ),
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
    ("church", re.compile(r"\bCHURCH\b|\bMINISTRIES\b|\bPARISH\b|\bDIOCESE\b", re.IGNORECASE)),
    ("school", re.compile(r"\bSCHOOLS?\b|\bUNIVERSITY\b|\bCOLLEGE\b|\bACADEMY\b", re.IGNORECASE)),
    (
        "nonprofit",
        re.compile(
            r"\bFOUNDATION\b|\bNON-?PROFIT\b|\bASSOCIATION\b|\bSOCIETY\b|\bCHARIT|"
            r"\bCONSERVANCY\b|\bHABITAT FOR HUMANITY\b",
            re.IGNORECASE,
        ),
    ),
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
    'towerco', 'utility', 'llc', 'trust', 'corporation', 'partnership', 'gov',
    'church', 'school', 'nonprofit', 'individual', 'unknown' (MACRO-7 / #222).
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
