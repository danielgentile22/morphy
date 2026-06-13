#!/usr/bin/env python3
"""THROWAWAY one-off audit (issue #11) — NOT part of the preprocess pipeline.

Answers the two questions #24 (the hybrid ULS↔ASR join) needs settled:

  (1) COVERAGE  — what fraction of in-scope ULS `LO` records carry a populated
      ``asr_number`` (the exact, high-precision ASR cross-reference key), per
      band and overall, plus the coordinate null/zero rate.
  (2) CALIBRATION — the asr_number-tagged records are a *labeled* set: each one
      pins a (ULS LO coord, ASR tower coord) pair for the SAME structure
      (join asr_number = ASR registration_number). The great-circle distance
      between those two coords is exactly how far ULS coordinates drift from the
      true tower location — the empirical basis for the proximity-fallback
      tolerance bands #24 will use for the records that LACK an asr_number.

Reads the #12 normalized `location` parquet (asr_number + decimal coords already
parsed) and the fcc_asr `towers` parquet (the ground-truth tower set). No raw
parsing, no DMS math needed — #12 did it.

Run:
    source .venv/bin/activate
    python scripts/audits/uls_asr_number_coverage.py

Prints markdown-ready tables on demand. The durable methodology note (bimodal
asr_number coverage + the drift-calibrated confidence tiers) lives in the FCC-ULS
caveats of docs/DATA_SOURCES.md §2-7; re-run this script for the full numbers.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
NORM = REPO / "data" / "processed" / "normalized"

# In-scope bands (ADR-053 §A): Cellular (Part 22) + PCS/AWS/700 (the Part 24/27
# service-code subset of the market bundle). WCS/Microwave stay deferred.
BANDS = {
    "cellular": NORM / "fcc_uls_cellular" / "location.parquet",
    "pcs": NORM / "fcc_uls_market" / "pcs" / "location.parquet",
    "aws": NORM / "fcc_uls_market" / "aws" / "location.parquet",
    "700mhz": NORM / "fcc_uls_market" / "700mhz" / "location.parquet",
}
ASR_TOWERS = NORM / "fcc_asr" / "towers.parquet"

# Phase-1 committed anchor states (CLAUDE.md §7) — calibration is restricted here
# (the towers we actually care about); national is reported as a stability check.
ANCHOR_FIPS = {"05": "AR", "12": "FL", "30": "MT", "54": "WV"}

CUTOFFS_M = [50, 100, 250, 500, 1000]


def haversine_m(lat1, lon1, lat2, lon2):
    """Great-circle distance in metres between coordinate arrays (EPSG:4326).

    Vectorised numpy — no heavy geo dep. Earth radius = mean radius 6_371_008.8 m.
    """
    r = 6_371_008.8
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlmb = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlmb / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def _haversine_selftest():
    """Cheap correctness guard — the whole calibration rides on this helper."""
    # NYC (40.7128,-74.0060) -> LA (34.0522,-118.2437) ~= 3,936 km (±10 km).
    d = haversine_m(40.7128, -74.0060, 34.0522, -118.2437)
    assert abs(d - 3_936_000) < 10_000, d
    # One degree of latitude ~= 111 km.
    assert abs(haversine_m(0.0, 0.0, 1.0, 0.0) - 111_195) < 200
    # Identity -> 0.
    assert haversine_m(34.0, -92.0, 34.0, -92.0) == 0.0


def _asr_populated(series: pd.Series) -> pd.Series:
    s = series.astype("string").str.strip()
    return s.notna() & (s != "") & (s.str.lower() != "nan")


def _coords_ok(df: pd.DataFrame) -> pd.Series:
    return df["lat"].notna() & df["lon"].notna() & (df["lat"] != 0) & (df["lon"] != 0)


def main() -> None:
    _haversine_selftest()

    # ---- load ----------------------------------------------------------------
    bands = {}
    for name, path in BANDS.items():
        if not path.exists():
            raise SystemExit(f"missing normalized parquet: {path} (run #12 normalizer first)")
        bands[name] = pd.read_parquet(
            path,
            columns=["asr_number", "lat", "lon", "location_state", "state_fips", "coord_status"],
        )

    asr = pd.read_parquet(ASR_TOWERS, columns=["asr_number", "lat", "lon", "state_fips"])
    asr["asr_number"] = asr["asr_number"].astype("string").str.strip()
    asr = asr.rename(columns={"lat": "asr_lat", "lon": "asr_lon", "state_fips": "asr_state_fips"})

    # ---- (1) COVERAGE --------------------------------------------------------
    print("\n## 1. asr_number coverage (in-scope ULS LO records)\n")
    print("| band | LO rows | asr_number populated | coords present | non-`ok` coord_status |")
    print("|---|---:|---:|---:|---:|")
    tot_rows = tot_pop = 0
    for name, df in bands.items():
        n = len(df)
        pop = int(_asr_populated(df["asr_number"]).sum())
        coords = int(_coords_ok(df).sum())
        bad_status = int((df["coord_status"].astype("string").str.lower() != "ok").sum())
        tot_rows += n
        tot_pop += pop
        print(
            f"| {name} | {n:,} | {pop:,} ({100 * pop / n:.1f}%) | {coords:,} ({100 * coords / n:.1f}%) | {bad_status} |"
        )
    print(
        f"| **all in-scope** | **{tot_rows:,}** | **{tot_pop:,} ({100 * tot_pop / tot_rows:.1f}%)** | | |"
    )

    # ---- (2) CALIBRATION -----------------------------------------------------
    # Only bands with populated asr_number contribute labeled pairs. Build the
    # union of tagged LO rows across all in-scope bands, join to ASR on
    # asr_number, and measure ULS-coord -> tower-coord drift.
    tagged = []
    for name, df in bands.items():
        sub = df[_asr_populated(df["asr_number"]) & _coords_ok(df)].copy()
        sub["band"] = name
        sub["asr_number"] = sub["asr_number"].astype("string").str.strip()
        tagged.append(sub[["asr_number", "lat", "lon", "location_state", "band"]])
    tagged = pd.concat(tagged, ignore_index=True)

    pairs = tagged.merge(asr, on="asr_number", how="inner")
    pairs["dist_m"] = haversine_m(
        pairs["lat"].to_numpy(),
        pairs["lon"].to_numpy(),
        pairs["asr_lat"].to_numpy(),
        pairs["asr_lon"].to_numpy(),
    )
    unmatched = len(tagged) - len(pairs)

    anchor = pairs[pairs["asr_state_fips"].isin(ANCHOR_FIPS)].copy()

    print("\n## 2. ULS-coord → ASR-tower-coord drift (labeled pairs)\n")
    print(f"- tagged LO rows (asr_number + valid coords): **{len(tagged):,}**")
    print(
        f"- matched to an ASR tower: **{len(pairs):,}** ({100 * len(pairs) / len(tagged):.1f}%); unmatched: {unmatched}"
    )
    print(f"- bands contributing pairs: {pairs['band'].value_counts().to_dict()}")
    print(f"- anchor-state (AR/MT/FL/WV) pairs: **{len(anchor):,}**\n")

    def dist_table(d: pd.Series, label: str) -> None:
        pct = {p: np.percentile(d, p) for p in (50, 75, 90, 95, 99)}
        print(f"\n### {label} (n={len(d):,})\n")
        print("| percentile | distance |")
        print("|---|---:|")
        for p, v in pct.items():
            print(f"| p{p} | {v:,.0f} m |")
        print(f"| max | {d.max():,.0f} m |")
        print(f"| mean | {d.mean():,.0f} m |")
        print("\n| cutoff | pairs ≤ cutoff | share |")
        print("|---|---:|---:|")
        for c in CUTOFFS_M:
            k = int((d <= c).sum())
            print(f"| ≤ {c} m | {k:,} | {100 * k / len(d):.1f}% |")

    dist_table(anchor["dist_m"], "Anchor states (AR/MT/FL/WV) — PRIMARY calibration")
    dist_table(pairs["dist_m"], "National — stability check")


if __name__ == "__main__":
    main()
