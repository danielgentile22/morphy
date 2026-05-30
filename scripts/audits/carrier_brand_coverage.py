#!/usr/bin/env python3
"""THROWAWAY one-off audit (issue #22) — NOT part of the preprocess pipeline.

Validates the `carrier_brands` rollup table against the real #12 normalized ULS
licensee strings, and surfaces the high-frequency tail (the next entities worth
a table row). Answers the two questions #22 cares about:

  (1) MAPPED-SHARE — what fraction of ULS licensee (EN entity_type 'L') strings
      map to a known consumer brand, reported three ways because the denominator
      matters a lot here:
        * by distinct entity name     — table breadth
        * by licensee row (all bands) — dominated by geographic-area auction
          holders (one license per market), so NOT subscriber share
        * by licensee row ON A REGISTERED TOWER (the LO row carries a populated
          asr_number) — the closest free proxy for "carriers actually on towers",
          which is what the co-founder sees. This is the headline number.
  (2) TAIL — the top unmapped entities under each weighting; the audit's real
      product (what to add next via the ADD-A-CARRIER workflow).

Reads the #12 normalized `entity` + `location` parquet only. No raw parsing.

Run:
    source .venv/bin/activate
    python scripts/audits/carrier_brand_coverage.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
NORM = REPO / "data" / "processed" / "normalized"
import sys  # noqa: E402 — keep imports near use; this is a throwaway script

sys.path.insert(0, str(REPO / "scripts"))
from preprocess.carrier_brands import carrier_for  # noqa: E402

BANDS = {
    "cellular": NORM / "fcc_uls_cellular",
    "pcs": NORM / "fcc_uls_market" / "pcs",
    "aws": NORM / "fcc_uls_market" / "aws",
    "700mhz": NORM / "fcc_uls_market" / "700mhz",
}
ANCHOR_FIPS = {"05", "12", "30", "54"}  # AR / FL / MT / WV


def _asr_populated(series: pd.Series) -> pd.Series:
    s = series.astype("string").str.strip()
    return s.notna() & (s != "") & (s.str.lower() != "nan")


def _load() -> tuple[pd.DataFrame, set[str], set[str]]:
    ents, on_tower, anchor = [], set(), set()
    for band, base in BANDS.items():
        e = pd.read_parquet(base / "entity.parquet", columns=["usi", "entity_type", "entity_name"])
        e = e[e["entity_type"] == "L"].copy()
        e["band"] = band
        ents.append(e)
        lo = pd.read_parquet(base / "location.parquet", columns=["usi", "asr_number", "state_fips"])
        tagged = lo[_asr_populated(lo["asr_number"])]
        on_tower |= set(tagged["usi"])
        anchor |= set(tagged[tagged["state_fips"].isin(ANCHOR_FIPS)]["usi"])
    return pd.concat(ents, ignore_index=True), on_tower, anchor


def _share(df: pd.DataFrame, label: str) -> None:
    n = len(df)
    mapped = int(df["is_mapped"].sum())
    print(f"\n### {label}")
    print(
        f"- rows: **{n:,}**  | mapped: **{mapped:,} ({100 * mapped / n:.1f}%)**  | tail: {n - mapped:,}"
    )
    print(f"- brands hit: {df.loc[df['is_mapped'], 'brand'].value_counts().to_dict()}")


def _top_unmapped(df: pd.DataFrame, label: str, k: int = 20) -> None:
    tail = df[~df["is_mapped"]]
    vc = tail["entity_name"].fillna("(blank)").value_counts().head(k)
    print(f"\n### Top {k} UNMAPPED — {label}\n")
    print("| count | raw entity_name |")
    print("|---:|---|")
    for name, ct in vc.items():
        print(f"| {ct:,} | {name} |")


def main() -> None:
    L, on_tower, anchor = _load()
    mapped = L["entity_name"].map(lambda s: carrier_for(None, s))
    L["brand"] = mapped.map(lambda t: t[0])
    L["is_mapped"] = mapped.map(lambda t: t[1])

    print("# Carrier-brand rollup coverage (issue #22)\n")
    print(f"- licensee (EN type 'L') rows across 4 bands: **{len(L):,}**")
    print(f"- distinct licensee names: **{L['entity_name'].nunique():,}**")

    # (1) distinct names
    distinct = L.drop_duplicates(subset="entity_name")
    _share(distinct, "By DISTINCT entity name")
    # (2) all licensee rows
    _share(L, "By licensee row (all bands — incl. geographic-area auction holders)")
    # (3) on a registered tower — the headline
    tower = L[L["usi"].isin(on_tower)]
    _share(tower, "By licensee row ON A REGISTERED TOWER (headline — closest 'on towers' proxy)")
    # The gap is dominated by entities left in the tail ON PURPOSE (ambiguous
    # legacy holders). Report the share once those are excluded, for honesty.
    is_alltel = tower["entity_name"].astype("string").str.upper().str.contains("ALLTEL", na=False)
    attributable = tower[~is_alltel]
    n, m = len(attributable), int(attributable["is_mapped"].sum())
    print(
        f"\n- on-tower share EXCLUDING deliberately-unmapped 'ALLTEL' "
        f"({int(is_alltel.sum()):,} rows): **{m:,}/{n:,} = {100 * m / n:.1f}%**"
    )
    anc = L[L["usi"].isin(anchor)]
    _share(anc, "By licensee row on a registered tower IN AN ANCHOR STATE (AR/FL/MT/WV)")

    _top_unmapped(distinct, "distinct names")
    _top_unmapped(tower, "on a registered tower")


if __name__ == "__main__":
    main()
