"""ARC County Economic Status (FY xlsx) → canonical `county_score`."""

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
from ._helpers import canon_county_fips, canon_state_fips, safe_str

log = logging.getLogger("preprocess.arc_distressed")

_TIER_ALIASES = {
    "distressed": "distressed",
    "at-risk": "at-risk",
    "at risk": "at-risk",
    "transitional": "transitional",
    "competitive": "competitive",
    "attainment": "attainment",
}


@register_normalizer
class ArcDistressedNormalizer(Normalizer):
    source_id = "arc_distressed"
    canonical_types = ["county_score"]

    def normalize(self, raw_dir: Path, out_dir: Path) -> NormalizeResult:
        xlsx = self._find_xlsx(raw_dir)
        if xlsx is None:
            raise FileNotFoundError(f"arc_distressed: no .xlsx found under {raw_dir}")

        # ARC workbook usually has one sheet per state plus a 'Counties' or
        # 'County Data' summary sheet with everything. Try to find it.
        all_sheets = pd.read_excel(xlsx, sheet_name=None, dtype=str)
        log.info("arc_distressed: %d sheets in %s", len(all_sheets), xlsx.name)

        # Pick the sheet that looks like the master table.
        master = self._pick_master_sheet(all_sheets)
        log.info("arc_distressed: master sheet = %s (%d rows)", master["_name"], len(master["df"]))
        df = master["df"]

        raw_bytes = write_raw_parquet(df, out_dir, name="raw.parquet")

        # Identify FIPS + tier columns.
        fips_col = self._find_col(df, ["FIPS", "County FIPS", "GEOID", "FIPS Code"])
        tier_col = self._find_col(df, ["Economic Status", "Status", "Economic Tier", "Tier"])
        state_col = self._find_col(df, ["State", "State Abbreviation", "ST"])

        if fips_col is None or tier_col is None:
            raise RuntimeError(
                f"arc_distressed: couldn't find FIPS column (tried various) or tier "
                f"column in {xlsx.name}. Columns present: {list(df.columns)}"
            )

        rows = []
        for _, r in df.iterrows():
            state_fips = canon_state_fips(r.get(state_col)) if state_col else None
            fips = canon_county_fips(r.get(fips_col), state_fips=state_fips)
            tier_raw = safe_str(r.get(tier_col)).lower()
            tier = _TIER_ALIASES.get(tier_raw, "")
            if not fips:
                continue
            rows.append(
                {
                    "county_fips": fips,
                    "state_fips": fips[:2] if fips else None,
                    "tier": tier,
                    "score": None,  # ARC publishes underlying score components separately
                    "persistent_poverty": None,  # comes from USDA, not ARC
                    "arc_distressed": tier == "distressed",
                    "arc_at_risk": tier == "at-risk",
                    "sources": ["arc"],
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
    def _find_xlsx(raw_dir: Path) -> Path | None:
        if not raw_dir.exists():
            return None
        cand = sorted(raw_dir.rglob("*.xlsx"))
        return cand[0] if cand else None

    @staticmethod
    def _pick_master_sheet(sheets: dict[str, pd.DataFrame]) -> dict:
        """Find the sheet that contains the per-county master table."""
        ranked = []
        for name, df in sheets.items():
            score = 0
            lower_cols = {str(c).lower() for c in df.columns}
            if any("fips" in c for c in lower_cols):
                score += 10
            if any("status" in c or "tier" in c for c in lower_cols):
                score += 5
            score += min(len(df), 500) / 100  # prefer big sheets
            ranked.append((score, name, df))
        ranked.sort(reverse=True)
        top = ranked[0]
        return {"_name": top[1], "df": top[2]}

    @staticmethod
    def _find_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
        lower = {str(c).strip().lower(): c for c in df.columns}
        for cand in candidates:
            key = cand.lower()
            if key in lower:
                return lower[key]
        # Fuzzy: substring match
        for cand in candidates:
            key = cand.lower()
            for k, orig in lower.items():
                if key in k or k in key:
                    return orig
        return None
