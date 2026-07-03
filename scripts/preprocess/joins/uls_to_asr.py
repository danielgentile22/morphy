"""Hybrid ULS↔ASR join — put the CARRIER on the TOWER (Slice A / #24).

This is the consumer of #11 (the tolerance calibration), #12 (the ULS
normalizer) and #22 (the carrier-brand rollup). It joins ULS spectrum
licenses (who holds spectrum, and roughly where) to the registered FCC ASR
structures, tags each match with a confidence level, runs the brand rollup
on the licensee name, and attaches the result to the ``tower`` canonical
type as a ``carriers`` list-of-struct. After this the Lead page / map (#28)
can show "AT&T + Verizon on this tower".

**Vocabulary (CONTEXT.md).** A CARRIER is the ULS spectrum LICENSEE on a
tower (this join). It is NOT the VENDOR / REGISTRANT — the tower-co that owns
the structure (American Tower, Crown Castle …), which comes from FCC ASR and
is Slice B. Do not conflate them.

----------------------------------------------------------------------------
MATCHING — the #11-calibrated hybrid strategy (FCC-ULS caveats in docs/DATA_SOURCES.md §2-7;
regenerate the full calibration with ``python scripts/audits/uls_asr_number_coverage.py``)
----------------------------------------------------------------------------
Each ULS ``location`` row is attached to exactly one tower, by the first of
two paths that fires:

1. **Cross-ref → ``verified``.** A location carrying a populated ``asr_number``
   (the FCC ASR registration number, the LO ``tower_registration_number``) is
   joined exactly to the FCC ASR tower with that ``registration_number``. No
   distance. Available on ~59% of Cellular rows and 0% of PCS/AWS/700 (the
   coverage is bimodal — #11 §1). The cross-ref is restricted to genuine
   ``fcc_asr`` towers: FAA obstruction structures carry their own 6-digit
   study numbers in ``asr_number`` that are NOT FCC registrations.

2. **Spatial fallback → ``likely`` / ``possible``.** Every location that did
   not cross-ref (no ``asr_number``, or an ``asr_number`` that matched no FCC
   ASR tower) is matched to its nearest FCC ASR tower: ``≤ 100 m`` → ``likely``,
   ``> 100 m and ≤ 500 m`` → ``possible``, ``> 500 m`` → no match (refused —
   beyond 500 m only ~0.1-0.4% of genuine co-located pairs remain, and that is
   where the data-entry-error tail lives). The 100/500 m thresholds are #11's,
   not guesses — do not loosen them. Distance is measured in EPSG:5070 (CONUS
   Albers, metres); the anchor states are all CONUS.

   Both paths target FCC ASR towers specifically (``_source == fcc_asr``), not
   the whole tower union. The ``tower`` type also carries FAA obstruction
   structures (``faa_oeaaa`` — windmills, transmission towers, …), but (a) #11's
   tolerances were calibrated on ULS↔**ASR** coordinate drift and are only valid
   for that pairing, and (b) FAA points are ~3× denser, so matching against them
   would let a windmill "steal" the nearest-tower slot from the real registered
   tower and attach a carrier to a structure that is not a registered antenna
   site. A real cell site is almost always ASR-registered, so confining the
   match to ASR towers loses little and avoids the false positives.

The licensee name on each matched location is run through #22's ``carrier_for``
→ a consumer brand (AT&T / Verizon / …) when the lineage is documented, else
the raw licensee string with ``is_mapped=False`` — we keep the honest tail
because the surface communicates PRESENCE, not brand recognition.

----------------------------------------------------------------------------
DATA-LOADING WRINKLE
----------------------------------------------------------------------------
``location`` carries ``state_fips`` (per-state) so it rides in the per-state
``ComposeContext``. ``license`` does NOT — it is national (``state_fips`` is
always None), so it is filtered out of the context and must be read directly
off the four bands' normalized ``license.parquet`` (a few hundred KB total).
The license rows supply the ``licensee_name`` + ``expired_date`` joined to a
location by ``usi``. Tests inject a ``license`` table into the context, which
takes precedence over the disk read.

Per-tower output — ``carriers`` is a list of structs, each:
    {carrier_name, callsign, license_expiry, license_status,
     license_status_desc, confidence_tag}
deduped by (carrier_name, callsign), keeping the best tag (verified > likely
> possible). A tower with no match gets an empty list. ``license_status``
(the ULS HD code — A/C/E/T/…) + its label ride along so the badge can
distinguish an active license from a cancelled/expired one riding through
the match (audit M-l / #216).
"""

from __future__ import annotations

import logging

import geopandas as gpd
import pandas as pd

from ..base import ComposeContext, Join, register_join
from ..carrier_brands import carrier_for

log = logging.getLogger("preprocess.uls_to_asr")

# #11-calibrated proximity thresholds (metres). Calibrated, not guesses.
LIKELY_M = 100.0
POSSIBLE_M = 500.0

# Confidence ordering for dedup: a higher rank wins for the same (carrier, callsign).
_TAG_RANK = {"verified": 3, "likely": 2, "possible": 1}

# Metric CRS for the proximity fallback — CONUS Albers Equal Area (metres).
_METRIC_CRS = "EPSG:5070"

# Normalized license parquets, by band. license is national (no state_fips), so
# the composer never loads it; read it straight off disk here.
_LICENSE_RELPATHS = [
    ("fcc_uls_cellular", "license.parquet"),
    ("fcc_uls_market/pcs", "license.parquet"),
    ("fcc_uls_market/aws", "license.parquet"),
    ("fcc_uls_market/700mhz", "license.parquet"),
]


def _clean_str(value) -> str | None:
    """A license field as a clean string, or None for blank / NaN."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip()
    return s or None


# License columns the join consumes: identity + expiry + status (audit M-l).
_LICENSE_COLS = ["usi", "licensee_name", "expired_date", "license_status", "license_status_desc"]


def load_uls_licenses() -> pd.DataFrame:
    """Read the four bands' normalized license tables off disk.

    Returns one row per ``usi`` with ``licensee_name`` + ``expired_date`` +
    ``license_status``/``license_status_desc``. National + small; safe to
    read whole. Missing band files are skipped.
    """
    from .. import NORMALIZED_ROOT  # local import — avoid an import cycle

    frames: list[pd.DataFrame] = []
    for rel, fname in _LICENSE_RELPATHS:
        path = NORMALIZED_ROOT / rel / fname
        if not path.exists():
            continue
        # Read whole (national + small), then project: a stale pre-#216
        # normalize output without the status columns still loads (→ None).
        frames.append(pd.read_parquet(path).reindex(columns=_LICENSE_COLS))
    if not frames:
        return pd.DataFrame(columns=_LICENSE_COLS)
    lic = pd.concat(frames, ignore_index=True)
    return lic.drop_duplicates(subset="usi", keep="first")


@register_join
class UlsToAsrJoin(Join):
    """Attach ULS carriers to towers (verified / likely / possible)."""

    name = "UlsToAsrJoin"
    inputs = ["tower", "location"]
    annotates = "tower"
    columns_added = ["carriers"]

    def apply(self, ctx: ComposeContext) -> None:
        towers = ctx.get("tower")
        locations = ctx.get("location")
        if towers is None or len(towers) == 0:
            return
        towers = towers.copy()
        # Stable positional key carried through every merge / sjoin.
        towers["__tidx"] = range(len(towers))

        if locations is None or len(locations) == 0:
            towers["carriers"] = [[] for _ in range(len(towers))]
            ctx.set("tower", towers)
            ctx.join_log.append(self.name)
            return

        locs = locations.copy()
        # licensee_name + expiry: prefer an injected context license table
        # (tests), else read the national license parquets off disk.
        lic = ctx.get("license")
        if lic is None or len(lic) == 0:
            lic = load_uls_licenses()
        # An injected test table may predate the status columns — default them
        # so a lean fixture still joins (status then rides as None → "").
        lic = lic.copy()
        for col in _LICENSE_COLS:
            if col not in lic.columns:
                lic[col] = None
        lic = lic[_LICENSE_COLS].drop_duplicates("usi", keep="first")
        locs = locs.merge(lic, on="usi", how="left")

        has_asr = locs["asr_number"].notna() & (
            locs["asr_number"].astype("string").str.strip().fillna("") != ""
        )

        # ── 1. Cross-ref → verified (genuine FCC ASR towers only) ───────────
        # Both match paths target FCC ASR towers (see module docstring): the
        # cross-ref key + #11's tolerances are only valid for ULS↔ASR.
        asr_towers = (
            towers[towers["_source"] == "fcc_asr"] if "_source" in towers.columns else towers
        )
        asr_key = (
            asr_towers.assign(_asr=asr_towers["asr_number"].astype("string").str.strip())[
                ["_asr", "__tidx"]
            ]
            .dropna(subset=["_asr"])
            .drop_duplicates(subset="_asr", keep="first")
        )
        matches: list[dict] = []
        matched_asr: set[str] = set()
        if len(asr_key) > 0:
            v = locs[has_asr].assign(
                _asr=locs.loc[has_asr, "asr_number"].astype("string").str.strip()
            )
            v = v.merge(asr_key, on="_asr", how="inner")
            matched_asr = set(v["_asr"])
            for rec in v.to_dict("records"):
                matches.append(self._entry(rec["__tidx"], rec, "verified"))

        # ── 2. Spatial fallback → likely / possible ─────────────────────────
        # Everything that did not cross-ref (no asr_number, or one that hit no
        # FCC ASR tower) falls back to nearest-tower proximity.
        crossed = has_asr & locs["asr_number"].astype("string").str.strip().isin(matched_asr)
        rest = locs[~crossed]
        coord_ok = (
            rest["coord_status"] == "ok"
            if "coord_status" in rest.columns
            else pd.Series(True, index=rest.index)
        )
        rest = rest[coord_ok & rest["lat"].notna() & rest["lon"].notna()]
        cand = asr_towers[asr_towers.geometry.notna()]
        if len(rest) > 0 and len(cand) > 0:
            left = gpd.GeoDataFrame(
                rest,
                geometry=gpd.points_from_xy(rest["lon"], rest["lat"]),
                crs="EPSG:4326",
            ).to_crs(_METRIC_CRS)
            right = cand[["__tidx", "geometry"]].to_crs(_METRIC_CRS)
            nearest = gpd.sjoin_nearest(
                left, right, how="inner", max_distance=POSSIBLE_M, distance_col="_dist_m"
            )
            for rec in nearest.to_dict("records"):
                tag = "likely" if rec["_dist_m"] <= LIKELY_M else "possible"
                matches.append(self._entry(rec["__tidx"], rec, tag))

        # ── 3. Per-tower dedup → carriers list-of-struct ────────────────────
        per_tower: dict[int, dict[tuple, dict]] = {}
        for m in matches:
            if m is None:
                continue
            tidx = m.pop("__tidx")
            key = (m["carrier_name"], m["callsign"])
            bucket = per_tower.setdefault(tidx, {})
            prev = bucket.get(key)
            if prev is None or _TAG_RANK[m["confidence_tag"]] > _TAG_RANK[prev["confidence_tag"]]:
                bucket[key] = m

        def _carriers_for(tidx: int) -> list[dict]:
            bucket = per_tower.get(tidx)
            if not bucket:
                return []
            # Deterministic order so the on-disk column is stable run-to-run.
            return sorted(
                bucket.values(), key=lambda e: (e["carrier_name"] or "", e["callsign"] or "")
            )

        towers["carriers"] = towers["__tidx"].map(_carriers_for)
        towers = towers.drop(columns="__tidx")
        ctx.set("tower", towers)
        ctx.join_log.append(self.name)

    @staticmethod
    def _entry(tidx, row: dict, tag: str) -> dict | None:
        """Build one carrier entry from a matched (location ⋈ license) record.

        ``carrier_for`` maps the licensee name to a brand (or keeps the raw
        tail name). A blank licensee yields no identifiable carrier → dropped.
        """
        callsign = row.get("callsign")
        licensee = row.get("licensee_name")
        carrier_name, _is_mapped = carrier_for(callsign, licensee)
        if carrier_name is None:
            return None
        cs = None
        if callsign is not None and not (isinstance(callsign, float) and pd.isna(callsign)):
            cs = str(callsign).strip() or None
        return {
            "__tidx": int(tidx),
            "carrier_name": carrier_name,
            "callsign": cs,
            "license_expiry": _clean_str(row.get("expired_date")),
            # ULS HD status (A/C/E/T/…) + label — lets the badge distinguish
            # an active license from a cancelled/expired one (audit M-l).
            "license_status": _clean_str(row.get("license_status")),
            "license_status_desc": _clean_str(row.get("license_status_desc")),
            "confidence_tag": tag,
        }


def carrier_coverage_summary(towers) -> dict:
    """Carrier-coverage stats for ``summary.json`` (the #24 acceptance gate).

    The headline ``coverage_pct`` is the AC metric: share of FCC ASR towers
    (``_source == fcc_asr``) carrying ≥ 1 identified carrier. ``by_confidence``
    counts those towers by their best (highest-confidence) tag. Whole-tower
    figures (incl. FAA structures) are reported alongside for context.
    """
    if towers is None or len(towers) == 0 or "carriers" not in towers.columns:
        return {"computed": False}

    def _has(v) -> bool:
        return isinstance(v, list) and len(v) > 0

    def _best(v) -> str | None:
        if not _has(v):
            return None
        return max((e.get("confidence_tag") for e in v), key=lambda t: _TAG_RANK.get(t, 0))

    has_carrier = towers["carriers"].map(_has)
    is_asr = towers["_source"] == "fcc_asr" if "_source" in towers.columns else towers.index >= 0

    asr = towers[is_asr]
    asr_has = has_carrier[is_asr]
    n_asr = int(len(asr))
    m_asr = int(asr_has.sum())

    by_conf = {"verified": 0, "likely": 0, "possible": 0}
    for v in asr["carriers"]:
        tag = _best(v)
        if tag in by_conf:
            by_conf[tag] += 1

    n_all = int(len(towers))
    m_all = int(has_carrier.sum())
    return {
        "computed": True,
        "asr_towers": n_asr,
        "asr_towers_with_carrier": m_asr,
        "coverage_pct": round(100 * m_asr / n_asr, 1) if n_asr else 0.0,
        "by_confidence": by_conf,
        "all_towers": n_all,
        "all_towers_with_carrier": m_all,
        "coverage_pct_all_towers": round(100 * m_all / n_all, 1) if n_all else 0.0,
    }
