"""Regrid (Landgrid) nationwide parcels — paid bulk license.

This source is **credentialed**: the puller only attempts it when the
following environment variables are set (typically loaded from a .env
file the user owns):

    REGRID_S3_BUCKET     — S3 bucket Regrid hosts your deliveries in
    REGRID_S3_PREFIX     — prefix under that bucket (your tenant)
    AWS_ACCESS_KEY_ID    — credentials Regrid issued you
    AWS_SECRET_ACCESS_KEY

Without credentials, the UI shows "Credentials required" and the
manual_url links to Regrid sales. With credentials, we use boto3 to mirror
the prefix into ``current/``.

Implementation note: boto3 is imported lazily so the rest of the puller
works without it. The CREDENTIALED policy means the puller never tries
to fetch without credentials, so we won't hit an import error in normal
operation.
"""

from __future__ import annotations

import os
from pathlib import Path

from ..base import (
    CATEGORY_PARCELS,
    DataSource,
    FetchResult,
    ProgressCallback,
)
from ..legal import AutomationPolicy, CommercialUse, LegalInfo

REQUIRED_ENV = (
    "REGRID_S3_BUCKET",
    "REGRID_S3_PREFIX",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
)


class RegridParcels(DataSource):
    id = "regrid_parcels"
    name = "Regrid (Landgrid) — nationwide parcels (PAID)"
    category = CATEGORY_PARCELS
    coverage = "Configurable: single state, regional bundle, or all 50 states"
    cadence = "Quarterly (or monthly at premium tier)"
    estimated_size_mb = 60000.0
    description = (
        "Nationwide normalised parcel dataset (~159M parcels). One schema "
        "across all counties — owner, mailing address, land use, value, "
        "acreage. Delivered to an S3 bucket on the schedule you license. "
        "Paid subscription: see DATA_SOURCES.md for tier guidance."
    )
    legal = LegalInfo(
        publisher="Regrid (Loveland Technologies)",
        license="Commercial bulk-data licence (per signed agreement)",
        license_url="https://regrid.com/api",
        automation=AutomationPolicy.CREDENTIALED,
        commercial_use=CommercialUse.ALLOWED,  # per licence terms
        # Sales contact page — no public download exists.
        manual_url="https://regrid.com/sales",
        attribution="Source: Regrid nationwide parcel data (licensed).",
        notes=(
            "PAID source — no public download. Process:\n"
            "\n"
            "1. Contact Regrid sales (manual URL above) for a quote. Tiers:\n"
            "   • Single state: ~$2K-$5K/year\n"
            "   • Regional bundle: ~$8K-$15K/year\n"
            "   • Nationwide: ~$15K-$50K/year\n"
            "\n"
            "2. Once licensed, Regrid provisions an S3 bucket with your "
            "tenant data. Get from them:\n"
            "   • S3 bucket name\n"
            "   • Prefix under the bucket (your tenant ID)\n"
            "   • AWS access key + secret (read-only for that prefix)\n"
            "\n"
            "3. Add to a .env file at the project root (gitignored):\n"
            "   REGRID_S3_BUCKET=...\n"
            "   REGRID_S3_PREFIX=...\n"
            "   AWS_ACCESS_KEY_ID=...\n"
            "   AWS_SECRET_ACCESS_KEY=...\n"
            "\n"
            "4. Restart the puller — the source flips from 'Credentials "
            "required' to actionable, and 'Pull' mirrors the entire prefix "
            "into data/raw/regrid_parcels/current/."
        ),
    )

    def credentials_available(self) -> bool:
        return all(os.environ.get(k) for k in REQUIRED_ENV)

    def remote_version(self) -> str:
        # Use the newest object's LastModified across the licensed prefix.
        bucket, prefix = os.environ["REGRID_S3_BUCKET"], os.environ["REGRID_S3_PREFIX"]
        s3 = self._s3_client()
        paginator = s3.get_paginator("list_objects_v2")
        latest = None
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []) or []:
                lm = obj.get("LastModified")
                if latest is None or (lm and lm > latest):
                    latest = lm
        if latest is None:
            raise RuntimeError("Regrid prefix is empty — check REGRID_S3_PREFIX")
        return latest.date().isoformat()

    def fetch(self, dest_dir: Path, progress: ProgressCallback) -> FetchResult:
        bucket, prefix = os.environ["REGRID_S3_BUCKET"], os.environ["REGRID_S3_PREFIX"]
        s3 = self._s3_client()
        paginator = s3.get_paginator("list_objects_v2")

        files: list[Path] = []
        total = 0
        # Two passes: first to compute aggregate size, second to download
        # (boto3 gives bytes per object but progress per-object aggregates
        # into a single overall figure for the UI).
        sizes: list[tuple[str, int]] = []
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []) or []:
                sizes.append((obj["Key"], obj["Size"]))
        grand_total = sum(s for _, s in sizes)

        downloaded = 0
        for key, size in sizes:
            rel = key[len(prefix) :].lstrip("/")
            target = dest_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            label = rel or key

            def _cb(n_bytes: int, _downloaded=downloaded, _label=label) -> None:
                progress(_downloaded + n_bytes, grand_total, _label)

            s3.download_file(bucket, key, str(target), Callback=_cb)
            files.append(target)
            downloaded += size
            total += size

        return FetchResult(
            files=files,
            remote_version=self.remote_version(),
            total_bytes=total,
        )

    def _s3_client(self):
        try:
            import boto3
        except ImportError as e:
            raise RuntimeError(
                "boto3 is required for Regrid downloads. Install with: pip install boto3"
            ) from e
        return boto3.client(
            "s3",
            aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
            aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
        )


SOURCE = RegridParcels()
