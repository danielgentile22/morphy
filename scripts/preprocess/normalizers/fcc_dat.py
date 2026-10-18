"""FCC pipe-delimited .dat readers + DMS coordinate parsing.

The FCC ships ASR and ULS bulk data as pipe-delimited ``.dat`` files
(no header row, one record type per file, mixed encodings). These
helpers know the format quirks; callers (currently ``fcc_asr``;
``fcc_uls`` later per ADR-013) pass an explicit column list.

DMS → decimal-degrees conversion also lives here because FCC ASR's
structure coordinates are split across separate degrees/minutes/
seconds/direction columns.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path

import pandas as pd

log = logging.getLogger("preprocess.normalizers")


def dms_to_decimal(deg, minutes, seconds, direction) -> float | None:
    """Convert separate degrees/minutes/seconds/direction fields → decimal."""
    try:
        d = float(deg) if deg not in (None, "", "nan") else None
        m = float(minutes) if minutes not in (None, "", "nan") else 0.0
        s = float(seconds) if seconds not in (None, "", "nan") else 0.0
    except (TypeError, ValueError):
        return None
    if d is None:
        return None
    val = abs(d) + m / 60.0 + s / 3600.0
    if direction in ("S", "W"):
        val = -val
    return val


def read_pipe_dat(
    path: Path,
    columns: list[str],
    record_type: str | None = None,
    *,
    encoding: str = "latin-1",
) -> pd.DataFrame:
    """Read a pipe-delimited .dat file with a known column list.

    If ``record_type`` is given, rows whose first field doesn't match are
    dropped (defensive guard against stray header/footer rows or mixed-record
    files). All columns are read as strings.
    """
    if not path.exists():
        raise FileNotFoundError(f"missing .dat file: {path}")
    log.debug("reading %s (%d cols)", path.name, len(columns))
    df = pd.read_csv(
        path,
        sep="|",
        header=None,
        names=columns,
        dtype=str,
        keep_default_na=False,
        na_values=[""],
        engine="python",
        on_bad_lines="warn",
        encoding=encoding,
        quoting=csv.QUOTE_NONE,
    )
    if record_type and columns and columns[0] == "record_type":
        before = len(df)
        df = df[df["record_type"] == record_type].copy()
        if len(df) != before:
            log.warning("dropped %d non-%s rows from %s", before - len(df), record_type, path.name)
    return df
