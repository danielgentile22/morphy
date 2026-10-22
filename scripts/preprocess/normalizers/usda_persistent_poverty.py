"""USDA ERS County Typology Codes (CSV) → canonical `county_score`.

The ERS CSV is long-form: one row per (county, attribute, year). We
pivot to one row per county with persistent_poverty as a boolean.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from ..base import (
    Normalizer,
    NormalizeResult,
    add_system_columns,
    quality_report,
    register_normalizer,
    write_quality_report,
)
from ..io import write_parquet, write_raw_parquet
from .fips import canon_county_fips
from .pandas_coerce import safe_str

log = logging.getLogger("preprocess.usda_pp")


@register_normalizer
class UsdaPersistentPovertyNormalizer(Normalizer):
    source_id = "usda_persistent_poverty"
    canonical_types = ["county_score"]

    def normalize(self, raw_dir: Path, out_dir: Path) -> NormalizeResult:
        csv = self._find_csv(raw_dir)
        if csv is None:
            raise FileNotFoundError(f"usda_persistent_poverty: no .csv under {raw_dir}")
        df = pd.read_csv(csv, dtype=str, low_memory=False)
        log.info("usda_pp: read %d rows from %s", len(df), csv.name)

        raw_bytes = write_raw_parquet(df, out_dir, name="raw.parquet")

        # CSV is long-form: one row per (FIPS, Attribute, Year). Find the
        # persistent-poverty attribute row per county.
        fips_col = next(
            (c for c in df.columns if str(c).lower() in ("fipstxt", "fips", "fipscode")),
            None,
        )
        attr_col = next(
            (c for c in df.columns if str(c).lower() in ("attribute", "variable", "code")),
            None,
        )
        value_col = next(
            (c for c in df.columns if str(c).lower() in ("value", "val")),
            None,
        )
        if not fips_col or not attr_col or not value_col:
            raise RuntimeError(
                f"usda_pp: expected FIPStxt + Attribute + Value columns; got {list(df.columns)}"
            )

        # Filter to persistent-poverty rows (latest year wins).
        mask = (
            df[attr_col]
            .astype(str)
            .str.contains("persistent.poverty", case=False, regex=True, na=False)
        )
        pp = df[mask].copy()
        log.info("usda_pp: %d persistent-poverty rows", len(pp))

        # Each county's "persistent_poverty" flag = any of its pp rows == 1.
        pp["fips_canon"] = pp[fips_col].apply(canon_county_fips)
        pp["val_bool"] = pp[value_col].apply(
            lambda v: safe_str(v) in ("1", "True", "true", "Y", "y")
        )

        grouped = pp.groupby("fips_canon")["val_bool"].any().reset_index()
        grouped = grouped[grouped["fips_canon"].notna()]

        rows = []
        for _, r in grouped.iterrows():
            fips = r["fips_canon"]
            rows.append(
                {
                    "county_fips": fips,
                    "state_fips": fips[:2] if fips else None,
                    "tier": "",
                    "score": None,
                    "persistent_poverty": bool(r["val_bool"]),
                    "arc_distressed": None,
                    "arc_at_risk": None,
                    "sources": ["usda_persistent_poverty"],
                }
            )
        scores = pd.DataFrame(rows)
        scores = add_system_columns(scores, self.source_id, "county_score")

        out_path = out_dir / "county_scores.parquet"
        out_bytes = write_parquet(scores, out_path)
        total = raw_bytes + out_bytes

        qr = quality_report(self.source_id, {"raw": df, "county_scores": scores})
        qr_path = write_quality_report(out_dir, qr)

        return NormalizeResult(
            raw_rows=len(df),
            canonical_rows=len(scores),
            bytes=total,
            output_files=[out_path, out_dir / "raw.parquet", qr_path],
            canonical_types_written=["county_score"],
            quality_report=qr,
        )

    @staticmethod
    def _find_csv(raw_dir: Path) -> Path | None:
        if not raw_dir.exists():
            return None
        cand = sorted(raw_dir.rglob("[!.]*.csv"))
        return cand[0] if cand else None
