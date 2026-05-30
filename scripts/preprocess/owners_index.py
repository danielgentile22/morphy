"""Cross-state owners index — the Lead-identity precompute (ADR-061 / ADR-056).

The per-state composites already cluster owners *within* a state by
``SHA1(normalized name + mailing address)`` (ADR-024). That key folds the
mailing address into the hash, so a national owner (AMERICAN TOWERS LLC,
WEYERHAEUSER, "UNITED STATES OF AMERICA") splits across its regional
mailing addresses — and always across state lines — into many clusters.

A **Lead is national**: one owner-cluster spanning every anchor state
(ADR-061). The cross-state merge key is therefore *name-anchored only* —
the address is dropped. We reuse the existing conservative owner-name
normaliser (``cluster.normalize_owner_name``: suffix strip + token sort)
and hash the normalised name into a stable ``display_cluster_id``. Exact
normalised-name match only — libpostal-grade normalisation is deferred
(ADR-056); the matcher errs toward *not* merging.

This is a read-only, cross-state tail step (a sibling of ``app_assets``):
it reads the per-state ``parcels_attr.parquet`` the facets step already
wrote and emits ``composite/owners_index.json``. No recompose.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from . import COMPOSITE_ROOT
from .app_assets import iter_composed_states
from .cluster import normalize_owner_name

OWNERS_INDEX_FILENAME = "owners_index.json"

# owners_index.json shape version — bump when the structure changes.
# v2 (Slice 3 / #49): each owner gains ``holdings`` (per-parcel detail +
# structures + footprint geometry), ``mailing_address`` (read-only source
# contact), and ``tallest_tower_height_m`` for the full Lead page.
OWNERS_INDEX_SCHEMA_VERSION = 2

# Best-parcel-anchored cluster score, with a modest portfolio-size bonus
# (ADR-056): score = max(parcel_scores) + ALPHA * ln(parcel_count).
DEFAULT_ALPHA = 0.1

# Distress tier severity ordering (the county-score normalizers emit
# exactly these strings, lowercased). Higher wins the cross-parcel rollup.
_TIER_RANK = {"": 0, "transitional": 1, "at-risk": 2, "distressed": 3}
_RANK_TIER = {v: k for k, v in _TIER_RANK.items()}

# Columns the resolver reads. Only these are pulled from the (large)
# per-state parquet so the precompute stays cheap. The trailing block
# (parcel_id … infrastructure_summary) feeds the per-owner ``holdings``
# + read-only mailing address the full Lead page needs (Slice 3 / #49);
# all are optional — a state missing one still rolls up.
INDEX_INPUT_COLUMNS = (
    "owner_name",
    "owner_name_norm",
    "owner_kind",
    "state_fips",
    "assessed_value",
    "tower_count",
    "solar_count",
    "has_tower",
    "has_solar",
    "interestingness_score",
    "distress_tier",
    "in_oz",
    "in_qct",
    "persistent_poverty",
    "parcel_id",
    "county_fips",
    "acreage",
    "land_use_desc",
    "geom_bbox",
    "infrastructure_summary",
    "mailing_addr",
    "mailing_city",
    "mailing_state",
    "mailing_zip",
)

# Tower-attribute columns joined onto a parcel's structures by ASR number
# (the ``infrastructure_summary`` tower ``id`` is the ASR number).
TOWER_ATTR_COLUMNS = (
    "asr_number",
    "height_m",
    "lat",
    "lon",
    "is_active",
    "structure_type_desc",
)

# Mailing-address placeholders that several state sources emit for "no
# address on file" — treated as empty so they never become a Lead's
# read-only contact.
_MAILING_JUNK = {"", "0", "0.0", "none", "null", "n/a", "unknown"}


def display_cluster_id(owner_name_norm: str) -> str:
    """Stable, name-anchored Lead id: first 12 hex of ``sha1(name_norm)``.

    Deterministic across recomputes (no address, no randomness) so a
    landowner keeps the same Lead key — and the same ``lead`` row — every
    time the index is rebuilt. Empty for an un-clusterable (blank) name.
    """
    if not owner_name_norm:
        return ""
    return hashlib.sha1(owner_name_norm.encode("utf-8")).hexdigest()[:12]


def _mode_or_empty(s: pd.Series) -> str:
    s = s.dropna().astype(str)
    s = s[s.str.strip() != ""]
    if s.empty:
        return ""
    m = s.mode()
    return str(m.iat[0]) if not m.empty else ""


def _to_float(value) -> float | None:
    """Best-effort float, tolerant of nulls / blank strings (returns None)."""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def _parse_json_list(raw) -> list[dict]:
    """Parse a JSON-array string column (e.g. ``infrastructure_summary``).

    Tolerant: a null, blank, or malformed value yields ``[]`` so a single
    bad row never breaks the holdings rollup. Accepts an already-parsed
    list too (the column can arrive pre-decoded).
    """
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    if not isinstance(raw, str) or not raw.strip():
        return []
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return []
    return [x for x in parsed if isinstance(x, dict)] if isinstance(parsed, list) else []


def _parse_bbox(raw) -> list[float] | None:
    """Parse a ``geom_bbox`` ``[minlng, minlat, maxlng, maxlat]`` (EPSG:4326).

    The preprocess pipeline reprojects every spatial output to WGS84, so
    the bbox is already lat/lon — usable directly as the mini-map footprint.
    Returns rounded floats, or None when absent/malformed.
    """
    if isinstance(raw, str):
        if not raw.strip():
            return None
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            return None
    if not isinstance(raw, (list, tuple)) or len(raw) != 4:
        return None
    out = [_to_float(v) for v in raw]
    if any(v is None for v in out):
        return None
    return [round(v, 6) for v in out]  # type: ignore[arg-type]


class CrossStateOwnerResolver:
    """Resolve per-state owner+parcel rows into cross-state Leads.

    Pure and I/O-free: ``resolve()`` takes a DataFrame of parcel rows
    (the columns in ``INDEX_INPUT_COLUMNS``) and returns the owners index
    — one row per ``display_cluster_id`` with the rollups the Candidates
    list and Lead page need. The driver (``run_owners_index``) supplies
    the structure-bearing parcels read off disk.
    """

    def __init__(
        self,
        alpha: float = DEFAULT_ALPHA,
        fips_to_abbr: dict[str, str] | Callable[[str], str] | None = None,
    ) -> None:
        self.alpha = alpha
        self._fips_to_abbr = fips_to_abbr

    def _abbr(self, fips: str) -> str:
        f = str(fips).zfill(2)
        if isinstance(self._fips_to_abbr, dict):
            return self._fips_to_abbr.get(f, f)
        if callable(self._fips_to_abbr):
            return self._fips_to_abbr(f)
        # Default: resolve via the authoritative state table; fall back to
        # the raw FIPS so an unknown code never crashes the rollup.
        try:
            from .geographies import get_state

            return get_state(f).abbr
        except Exception:
            return f

    def resolve(
        self, parcels: pd.DataFrame, towers_by_asr: dict[str, dict] | None = None
    ) -> pd.DataFrame:
        """Cluster parcels by normalized owner name → owners index.

        Rows with a blank normalized name are dropped (un-clusterable —
        can't be a Lead). Returns a DataFrame sorted by rolled-up score
        descending; empty input yields an empty, correctly-typed frame.

        ``towers_by_asr`` (optional) maps an ASR number → tower attributes
        (height/lat/lon/active); it enriches each parcel's structures so
        the per-owner ``holdings`` + ``tallest_tower_height_m`` carry real
        tower detail. Absent ⇒ structures still list their ASR ids, just
        without height/coordinates.
        """
        df = parcels.copy()
        if df.empty:
            return self._empty_index()

        # Prefer the pipeline's precomputed owner_name_norm (keeps the key
        # identical to the analytical layers); recompute from owner_name
        # for any row missing it so the resolver also works on raw rows.
        if "owner_name_norm" in df.columns:
            norm = df["owner_name_norm"].astype("string").fillna("")
            blank = norm.str.strip() == ""
            if blank.any():
                norm = norm.mask(blank, df.loc[blank, "owner_name"].map(normalize_owner_name))
        else:
            norm = df["owner_name"].map(normalize_owner_name)
        df["_norm"] = norm.astype(str).str.strip()
        df = df[df["_norm"] != ""]
        if df.empty:
            return self._empty_index()

        df["_cluster"] = df["_norm"].map(display_cluster_id)

        # Numeric/boolean coercions — nulls never reach the rollup. ``_col``
        # tolerates a column being absent entirely (returns an aligned
        # default Series), so a state missing one optional attribute still
        # rolls up instead of crashing.
        def _col(name, default):
            return df[name] if name in df.columns else pd.Series(default, index=df.index)

        df["_assessed"] = pd.to_numeric(_col("assessed_value", 0.0), errors="coerce").fillna(0.0)
        df["_score"] = pd.to_numeric(_col("interestingness_score", 0.0), errors="coerce").fillna(
            0.0
        )
        df["_towers"] = pd.to_numeric(_col("tower_count", 0), errors="coerce").fillna(0).astype(int)
        df["_solar"] = pd.to_numeric(_col("solar_count", 0), errors="coerce").fillna(0).astype(int)
        df["_tier_rank"] = (
            _col("distress_tier", "")
            .astype("string")
            .fillna("")
            .str.lower()
            .map(_TIER_RANK)
            .fillna(0)
            .astype(int)
        )
        for col in ("in_oz", "in_qct", "persistent_poverty"):
            df[f"_{col}"] = _col(col, False).fillna(False).astype(bool)

        # state_fips + owner_kind are contractual, but guard anyway so a
        # malformed input degrades to empty values rather than a KeyError.
        if "state_fips" not in df.columns:
            df["state_fips"] = ""
        if "owner_kind" not in df.columns:
            df["owner_kind"] = ""

        g = df.groupby("_cluster", sort=False)
        out = g.agg(
            owner_name=("owner_name", _mode_or_empty),
            owner_name_norm=("_norm", "first"),
            owner_kind=("owner_kind", _mode_or_empty),
            parcel_count=("_cluster", "size"),
            tower_count=("_towers", "sum"),
            solar_count=("_solar", "sum"),
            total_assessed_value=("_assessed", "sum"),
            max_parcel_score=("_score", "max"),
            _tier_rank=("_tier_rank", "max"),
            in_oz=("_in_oz", "any"),
            in_qct=("_in_qct", "any"),
            persistent_poverty=("_persistent_poverty", "any"),
            _fips=("state_fips", lambda s: sorted({str(v).zfill(2) for v in s.dropna()})),
        ).reset_index(names="display_cluster_id")

        out["states"] = out["_fips"].map(lambda fl: [self._abbr(f) for f in fl])
        out["n_states"] = out["states"].map(len)
        out["cross_state"] = out["n_states"] >= 2
        out["distress_tier"] = out["_tier_rank"].map(_RANK_TIER)
        out["score"] = (
            out["max_parcel_score"] + self.alpha * out["parcel_count"].map(lambda n: math.log(n))
        ).round(4)
        out["max_parcel_score"] = out["max_parcel_score"].round(4)
        out["total_assessed_value"] = out["total_assessed_value"].round(2)

        # Per-owner holdings + mailing + tallest tower (Slice 3 / #49). A
        # second pass over the same clusters keeps the rollup ``agg`` above
        # untouched; the cluster count (a few thousand) makes the python
        # loop cheap.
        detail = self._build_detail(df, towers_by_asr or {})
        out["holdings"] = out["display_cluster_id"].map(lambda c: detail[c][0])
        out["mailing_address"] = out["display_cluster_id"].map(lambda c: detail[c][1])
        out["tallest_tower_height_m"] = out["display_cluster_id"].map(lambda c: detail[c][2])

        out = out.drop(columns=["_fips", "_tier_rank"])
        return out.sort_values("score", ascending=False, ignore_index=True)

    # ── per-owner holdings detail ────────────────────────────────────────────
    def _build_detail(
        self, df: pd.DataFrame, towers_by_asr: dict[str, dict]
    ) -> dict[str, tuple[list[dict], dict | None, float | None]]:
        """``display_cluster_id`` → (holdings, mailing_address, tallest_m)."""
        detail: dict[str, tuple[list[dict], dict | None, float | None]] = {}
        for cid, group in df.groupby("_cluster", sort=False):
            recs = group.to_dict("records")
            holdings = [self._holding(r, towers_by_asr) for r in recs]
            tallest = max(
                (
                    s["height_m"]
                    for h in holdings
                    for s in h["structures"]
                    if s.get("type") == "tower" and s.get("height_m") is not None
                ),
                default=None,
            )
            detail[str(cid)] = (holdings, self._pick_mailing(recs), tallest)
        return detail

    def _holding(self, rec: dict, towers_by_asr: dict[str, dict]) -> dict:
        bbox = _parse_bbox(rec.get("geom_bbox"))
        structures = self._structures(rec.get("infrastructure_summary"), towers_by_asr)
        return {
            "parcel_id": str(rec.get("parcel_id") or ""),
            "state": self._abbr(rec.get("state_fips", "")),
            "county_fips": str(rec.get("county_fips") or ""),
            "land_use": str(rec.get("land_use_desc") or ""),
            "assessed_value": round(float(rec.get("_assessed", 0.0) or 0.0), 2),
            "acreage": _to_float(rec.get("acreage")),
            "tower_count": int(rec.get("_towers", 0) or 0),
            "solar_count": int(rec.get("_solar", 0) or 0),
            "bbox": bbox,
            "point": self._holding_point(structures, bbox),
            "structures": structures,
        }

    @staticmethod
    def _structures(raw, towers_by_asr: dict[str, dict]) -> list[dict]:
        out: list[dict] = []
        for item in _parse_json_list(raw):
            kind = str(item.get("type", ""))
            sid = str(item.get("id", ""))
            if kind == "tower":
                t = towers_by_asr.get(sid, {})
                out.append(
                    {
                        "type": "tower",
                        "asr": sid,
                        "height_m": _to_float(t.get("height_m")),
                        "lat": _to_float(t.get("lat")),
                        "lon": _to_float(t.get("lon")),
                        "active": (
                            None if t.get("is_active") is None else bool(t.get("is_active"))
                        ),
                        "structure_kind": str(t.get("structure_type_desc") or ""),
                    }
                )
            elif kind == "solar":
                out.append({"type": "solar", "id": sid, "owner": str(item.get("owner", "") or "")})
        return out

    @staticmethod
    def _holding_point(structures: list[dict], bbox: list[float] | None) -> list[float] | None:
        """A representative [lng, lat] for the mini-map. Prefer the parcel
        bbox centroid (the parcel's own, self-consistent footprint) over a
        tower coordinate — the ASR→parcel join is occasionally noisy, so a
        tower's lat/lon can land off its parcel. Exact tower coordinates
        still ride on each structure for callers that want them."""
        if bbox is not None:
            return [round((bbox[0] + bbox[2]) / 2, 6), round((bbox[1] + bbox[3]) / 2, 6)]
        for s in structures:
            if s.get("type") == "tower" and s.get("lat") is not None and s.get("lon") is not None:
                return [round(float(s["lon"]), 6), round(float(s["lat"]), 6)]
        return None

    @staticmethod
    def _pick_mailing(recs: list[dict]) -> dict | None:
        """The owner's read-only mailing address: the modal non-junk address
        across their parcels (a portfolio owner's canonical office)."""
        from collections import Counter

        counts: Counter[tuple[str, str, str, str]] = Counter()
        for r in recs:
            addr = str(r.get("mailing_addr") or "").strip()
            if addr.lower() in _MAILING_JUNK:
                continue
            counts[
                (
                    addr,
                    str(r.get("mailing_city") or "").strip(),
                    str(r.get("mailing_state") or "").strip(),
                    str(r.get("mailing_zip") or "").strip(),
                )
            ] += 1
        if not counts:
            return None
        addr, city, state, zip_ = counts.most_common(1)[0][0]
        return {"addr": addr, "city": city, "state": state, "zip": zip_}

    @staticmethod
    def _empty_index() -> pd.DataFrame:
        return pd.DataFrame(
            {
                "display_cluster_id": pd.Series(dtype="object"),
                "owner_name": pd.Series(dtype="object"),
                "owner_name_norm": pd.Series(dtype="object"),
                "owner_kind": pd.Series(dtype="object"),
                "parcel_count": pd.Series(dtype="int64"),
                "tower_count": pd.Series(dtype="int64"),
                "solar_count": pd.Series(dtype="int64"),
                "total_assessed_value": pd.Series(dtype="float64"),
                "max_parcel_score": pd.Series(dtype="float64"),
                "in_oz": pd.Series(dtype="bool"),
                "in_qct": pd.Series(dtype="bool"),
                "persistent_poverty": pd.Series(dtype="bool"),
                "states": pd.Series(dtype="object"),
                "n_states": pd.Series(dtype="int64"),
                "cross_state": pd.Series(dtype="bool"),
                "distress_tier": pd.Series(dtype="object"),
                "score": pd.Series(dtype="float64"),
                "holdings": pd.Series(dtype="object"),
                "mailing_address": pd.Series(dtype="object"),
                "tallest_tower_height_m": pd.Series(dtype="float64"),
            }
        )


# ── I/O driver (read-only tail step) ────────────────────────────────────────


def _read_state_parcels(state_dir: Path) -> pd.DataFrame:
    """Read the structure-bearing parcels for one state.

    Uses the slim ``parcels_attr.parquet`` the facets step writes (small,
    attribute-only). Returns only parcels that host a tower or solar
    facility — the Lead universe (a ground-lease lead must have an asset)
    and what keeps the index a few thousand owners rather than millions.
    """
    attr = state_dir / "parcels_attr.parquet"
    if not attr.exists():
        return pd.DataFrame()
    cols = pq_columns(attr)
    wanted = [c for c in INDEX_INPUT_COLUMNS if c in cols]
    df = pd.read_parquet(attr, columns=wanted)
    has_tower = df.get("has_tower", False)
    has_solar = df.get("has_solar", False)
    mask = pd.Series(has_tower, index=df.index).fillna(False).astype(bool) | pd.Series(
        has_solar, index=df.index
    ).fillna(False).astype(bool)
    return df[mask].copy()


def pq_columns(path: Path) -> set[str]:
    import pyarrow.parquet as pq

    return set(pq.read_schema(path).names)


def _read_state_towers(state_dir: Path) -> dict[str, dict]:
    """Map ``asr_number → {height_m, lat, lon, is_active, structure_type_desc}``
    for one state, used to enrich a parcel's structures with real tower
    detail. Missing file ⇒ empty map (structures keep only their ASR ids)."""
    towers = state_dir / "towers.parquet"
    if not towers.exists():
        return {}
    cols = pq_columns(towers)
    wanted = [c for c in TOWER_ATTR_COLUMNS if c in cols]
    if "asr_number" not in wanted:
        return {}
    df = pd.read_parquet(towers, columns=wanted)
    out: dict[str, dict] = {}
    for rec in df.to_dict("records"):
        asr = str(rec.get("asr_number") or "").strip()
        if asr:
            out[asr] = rec
    return out


def build_owners_index(composite_root: Path | None = None, alpha: float = DEFAULT_ALPHA) -> dict:
    """Read every composed anchor state and assemble the owners index dict.

    Reads ``parcels_attr.parquet`` (the facets output) plus ``towers.parquet``
    per state, so ``--app-assets`` must have run first. States without the
    parcel attributes are skipped.
    """
    root = composite_root if composite_root is not None else COMPOSITE_ROOT

    def _has_attr(d: Path) -> bool:
        return (d / "parcels_attr.parquet").exists()

    frames: list[pd.DataFrame] = []
    states_used: list[str] = []
    towers_by_asr: dict[str, dict] = {}
    for fips in iter_composed_states(root, predicate=_has_attr):
        part = _read_state_parcels(root / fips)
        if not part.empty:
            frames.append(part)
            states_used.append(fips)
            towers_by_asr.update(_read_state_towers(root / fips))

    resolver = CrossStateOwnerResolver(alpha=alpha)
    if frames:
        index_df = resolver.resolve(
            pd.concat(frames, ignore_index=True), towers_by_asr=towers_by_asr
        )
    else:
        index_df = resolver._empty_index()

    owners = [_owner_to_json(row) for row in index_df.to_dict("records")]
    return {
        "schema_version": OWNERS_INDEX_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "alpha": alpha,
        "states": sorted(states_used),
        "count": len(owners),
        "owners": owners,
    }


def _owner_to_json(row: dict) -> dict:
    """Coerce one index row to plain JSON-serialisable types."""
    return {
        "display_cluster_id": str(row["display_cluster_id"]),
        "owner_name": str(row["owner_name"]),
        "owner_name_norm": str(row["owner_name_norm"]),
        "owner_kind": str(row["owner_kind"]),
        "states": list(row["states"]),
        "n_states": int(row["n_states"]),
        "cross_state": bool(row["cross_state"]),
        "parcel_count": int(row["parcel_count"]),
        "tower_count": int(row["tower_count"]),
        "solar_count": int(row["solar_count"]),
        "total_assessed_value": float(row["total_assessed_value"]),
        "max_parcel_score": float(row["max_parcel_score"]),
        "score": float(row["score"]),
        "distress_tier": str(row["distress_tier"]),
        "in_oz": bool(row["in_oz"]),
        "in_qct": bool(row["in_qct"]),
        "persistent_poverty": bool(row["persistent_poverty"]),
        # Slice 3 / #49 — full Lead page detail (schema v2).
        "holdings": list(row.get("holdings") or []),
        "mailing_address": row.get("mailing_address") or None,
        "tallest_tower_height_m": _to_float(row.get("tallest_tower_height_m")),
    }


def write_owners_index(
    composite_root: Path | None = None,
    index_path: Path | None = None,
    alpha: float = DEFAULT_ALPHA,
) -> Path:
    """Build and write ``composite/owners_index.json`` atomically.

    Temp file + ``os.replace`` so the backend never reads a half-written
    index (the repo-wide atomic-write convention). Returns the path.
    """
    root = composite_root if composite_root is not None else COMPOSITE_ROOT
    if index_path is None:
        index_path = root / OWNERS_INDEX_FILENAME
    index = build_owners_index(root, alpha=alpha)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=index_path.parent, prefix=".owners_index.", suffix=".tmp"
    )
    try:
        with os.fdopen(tmp_fd, "w") as f:
            json.dump(index, f, indent=2, sort_keys=True)
        os.replace(tmp_path, index_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    return index_path


def run_owners_index(progress_callback=None) -> dict:
    """Write the cross-state owners index and return a small result dict."""
    index_path = write_owners_index()
    index = json.loads(index_path.read_text())
    n_owners = index.get("count", 0)
    n_cross = sum(1 for o in index.get("owners", []) if o.get("cross_state"))
    if progress_callback:
        progress_callback(
            "owners_index",
            "index",
            {"path": str(index_path), "owners": n_owners, "cross_state": n_cross},
        )
    return {
        "index_path": str(index_path),
        "owners": n_owners,
        "cross_state_owners": n_cross,
        "states": index.get("states", []),
    }
