"""Shared ArcGIS Hub source mechanics (#258).

The HUD distress overlays are ArcGIS Hub FeatureServer layers with an
identical fetch surface; the fragile publisher-facing pieces (the
edit-date version probe, the query-all fetch with its size guard, the
FeatureCollection validation) live here once so a publisher restructure
is fixed in one place. NC OneMap reuses the probe; its paginated
MapServer fetch is legitimately custom and stays in its module.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from ..base import DataSource, FetchResult, ProgressCallback
from ..http import HttpError, fetch_text
from ._helpers import arcgis_query_all


def arcgis_edit_date_version(meta_url: str, *, label: str) -> str:
    """Layer version = ``editingInfo.lastEditDate`` (epoch ms) as an ISO date.

    Falls back to ``n-<service name>`` when the service reports no edit
    date, so a service rename still surfaces as a version change. Raises
    ``HttpError`` when the metadata response isn't JSON.
    """
    text = fetch_text(meta_url)
    try:
        meta = json.loads(text)
    except json.JSONDecodeError as e:
        raise HttpError(f"{label} metadata not JSON: {e}")
    edit_ms = (meta.get("editingInfo") or {}).get("lastEditDate")
    if isinstance(edit_ms, (int, float)):
        return datetime.fromtimestamp(edit_ms / 1000, tz=UTC).date().isoformat()
    return f"n-{meta.get('name', '?')}"


class ArcGisHubSource(DataSource):
    """Base for ArcGIS Hub FeatureServer layers fetched via query-all.

    A subclass is pure configuration: the usual DataSource identity
    fields plus ``layer_url``, ``out_name``, ``error_label``, and
    optionally ``min_fetch_bytes``. Probe, fetch, and validation are
    owned here.
    """

    layer_url: str = ""
    out_name: str = ""  # output GeoJSON filename under current/
    error_label: str = ""  # human prefix on probe/fetch/validate errors
    min_fetch_bytes: int = 500_000  # a smaller payload is an incomplete pull

    @property
    def meta_url(self) -> str:
        return f"{self.layer_url}?f=pjson"

    def remote_version(self) -> str:
        return arcgis_edit_date_version(self.meta_url, label=self.error_label)

    def fetch(self, dest_dir: Path, progress: ProgressCallback) -> FetchResult:
        rv = self.remote_version()  # capture once; avoid 2nd probe post-download
        out = dest_dir / self.out_name
        n = arcgis_query_all(
            self.layer_url,
            out,
            lambda done, tot: progress(done, tot, self.out_name),
        )
        if n < self.min_fetch_bytes:
            raise HttpError(f"{self.error_label} download only {n} bytes — incomplete")
        return FetchResult(files=[out], remote_version=rv, total_bytes=n)

    def validate(self, files: list[Path]) -> None:
        super().validate(files)
        with open(files[0]) as f:
            head = f.read(2048)
        if '"FeatureCollection"' not in head:
            raise ValueError(f"{self.error_label} download is not a GeoJSON FeatureCollection")
