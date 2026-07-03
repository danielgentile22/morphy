"""Helpers shared across source modules.

Kept deliberately small — anything used by 2+ sources lands here, anything
specific to one source stays in that source file.
"""

from __future__ import annotations

import json
import zipfile
from collections.abc import Callable
from pathlib import Path

from ..http import HttpError, download, fetch_text, head


def version_from_head(url: str, *, label: str = "") -> str:
    """HEAD ``url`` and derive a stable version string.

    Tries Last-Modified → ETag → Content-Length in that order. Raises
    ``RuntimeError`` when none of those are present (a misconfigured
    publisher; better to surface than silently version with timestamps).
    """
    h = head(url)
    lm = parse_http_date(h.get("last_modified"))
    if lm:
        return lm
    etag = h.get("etag")
    if etag:
        return etag.strip('"')
    cl = h.get("content_length")
    if cl:
        return f"len-{cl}"
    raise RuntimeError(f"could not derive remote version{' for ' + label if label else ''}")


def safe_extract_zip(zip_path: Path, dest: Path) -> list[Path]:
    """Extract a zip while protecting against path-traversal.

    Returns the list of extracted file paths.
    """
    extracted: list[Path] = []
    with zipfile.ZipFile(zip_path) as z:
        for member in z.infolist():
            # Reject absolute paths and any '..' component
            name = member.filename
            if name.endswith("/"):
                continue
            target = (dest / name).resolve()
            if not str(target).startswith(str(dest.resolve())):
                raise ValueError(f"unsafe path in zip: {name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(member) as src, open(target, "wb") as out:
                while True:
                    chunk = src.read(1024 * 64)
                    if not chunk:
                        break
                    out.write(chunk)
            extracted.append(target)
    return extracted


def fetch_zip_extracted(
    url: str,
    dest_dir: Path,
    progress: Callable[[int, int | None, str], None],
    *,
    zip_name: str,
    extract_to: Path | None = None,
    expected_min_bytes: int = 0,
    progress_offset: int = 0,
    progress_total: int | None = None,
) -> tuple[list[Path], int]:
    """Download a zip into ``dest_dir``, safe-extract it, delete the zip.

    The manual-upload flow extracts zips in place, so auto-fetchers using
    this produce the exact same on-disk layout the normalizers already
    read. Returns ``(extracted files, zip bytes downloaded)``. Multi-file
    fetches pass ``progress_offset``/``progress_total`` so the bar tracks
    the cumulative fetch, not each individual zip.
    """
    zip_path = dest_dir / zip_name

    def on_progress(done: int, total: int | None) -> None:
        progress(
            progress_offset + done,
            progress_total if progress_total is not None else total,
            zip_name,
        )

    n = download(url, zip_path, on_progress, expected_min_bytes=expected_min_bytes)
    extracted = safe_extract_zip(zip_path, extract_to if extract_to is not None else dest_dir)
    zip_path.unlink()
    return extracted, n


def parse_http_date(value: str | None) -> str | None:
    """Normalise an HTTP Last-Modified value to ISO date.

    Returns the original string if parsing fails — version comparisons
    are by string equality, so consistent input → consistent output is
    all we need.
    """
    if not value:
        return None
    try:
        from email.utils import parsedate_to_datetime

        dt = parsedate_to_datetime(value)
        return dt.date().isoformat()
    except Exception:
        return value


def arcgis_query_all(
    layer_url: str,
    dest: Path,
    on_progress: Callable[[int, int | None], None] | None = None,
    page_size: int = 2000,
) -> int:
    """Download every feature from an ArcGIS FeatureServer layer as one GeoJSON.

    ArcGIS REST query endpoints cap a single response at the layer's
    ``maxRecordCount`` (commonly 2000). For full extracts of layers with
    more features (HUD OZ has ~8,700; QCT has ~17,000) we have to paginate
    via ``resultOffset`` and stitch the resulting feature arrays together.

    Writes a single FeatureCollection to ``dest`` and returns total bytes.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    base = f"{layer_url}/query"
    common = "where=1%3D1&outFields=*&f=geojson&returnGeometry=true"

    all_features: list = []
    offset = 0
    while True:
        url = f"{base}?{common}&resultOffset={offset}&resultRecordCount={page_size}"
        text = fetch_text(url, max_bytes=200 * 1024 * 1024)
        try:
            page = json.loads(text)
        except json.JSONDecodeError as e:
            raise HttpError(f"ArcGIS pagination JSON parse error at offset {offset}: {e}")
        if "error" in page:
            raise HttpError(f"ArcGIS error at offset {offset}: {page['error']}")
        feats = page.get("features", [])
        if not feats:
            break
        all_features.extend(feats)
        if on_progress is not None:
            on_progress(len(all_features), None)
        exceeded = page.get("properties", {}).get("exceededTransferLimit") or page.get(
            "exceededTransferLimit"
        )
        if not exceeded:
            break
        offset += len(feats)

    out = {"type": "FeatureCollection", "features": all_features}
    payload = json.dumps(out).encode("utf-8")
    tmp = dest.with_suffix(dest.suffix + ".partial")
    tmp.write_bytes(payload)
    tmp.replace(dest)
    if on_progress is not None:
        on_progress(len(payload), len(payload))
    return len(payload)
