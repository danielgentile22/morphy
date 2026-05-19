"""Shared HTTP helpers.

We use urllib (stdlib) rather than requests/httpx to avoid pulling extra
deps into the standalone app. The helpers below give us:

  * head(url) -> dict          ETag, Last-Modified, Content-Length
  * download(url, dest, on_progress, ...) — streaming, atomic, retried
  * fetch_text(url) -> str     small GETs (HTML pages, JSON metadata)

All requests carry a polite User-Agent that identifies the app, so
publishers can see this is not anonymous scraping.
"""

from __future__ import annotations

import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

USER_AGENT = "PilotDataPuller/0.1 (lease-optimization research; contact: 43241327+danielgentile22@users.noreply.github.com)"

DEFAULT_TIMEOUT = 60  # seconds, per download request
PROBE_TIMEOUT = 15  # seconds, per HEAD / cheap metadata GET
CHUNK = 1024 * 64  # 64 KiB streaming chunk
RETRY_DELAYS = (1, 4, 16)  # exponential backoff between attempts


class HttpError(RuntimeError):
    """Raised on irrecoverable HTTP failures."""


def _opener() -> urllib.request.OpenerDirector:
    opener = urllib.request.build_opener()
    opener.addheaders = [("User-Agent", USER_AGENT)]
    return opener


def head(url: str) -> dict[str, str | None]:
    """Return key response headers via HTTP HEAD.

    Keys: 'etag', 'last_modified', 'content_length', 'content_type'.
    Values may be None when the server omits the header.
    """
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=PROBE_TIMEOUT) as resp:
            h = resp.headers
            return {
                "etag": h.get("ETag"),
                "last_modified": h.get("Last-Modified"),
                "content_length": h.get("Content-Length"),
                "content_type": h.get("Content-Type"),
                "status": str(resp.status),
            }
    except urllib.error.HTTPError as e:
        # Some servers reject HEAD; fall back to a ranged GET of zero bytes
        if e.code in (403, 405, 501):
            return _head_via_get(url)
        raise HttpError(f"HEAD {url} → HTTP {e.code}") from e
    except (TimeoutError, urllib.error.URLError) as e:
        raise HttpError(f"HEAD {url} → {e}") from e


def _head_via_get(url: str) -> dict[str, str | None]:
    """Fallback when HEAD isn't supported: issue a Range: bytes=0-0 GET."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Range": "bytes=0-0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=PROBE_TIMEOUT) as resp:
            h = resp.headers
            cl = h.get("Content-Range")
            length = None
            if cl and "/" in cl:
                try:
                    length = cl.rsplit("/", 1)[1]
                except Exception:
                    length = None
            return {
                "etag": h.get("ETag"),
                "last_modified": h.get("Last-Modified"),
                "content_length": length or h.get("Content-Length"),
                "content_type": h.get("Content-Type"),
                "status": str(resp.status),
            }
    except (TimeoutError, urllib.error.HTTPError, urllib.error.URLError) as e:
        raise HttpError(f"GET-as-HEAD {url} → {e}") from e


def fetch_text(url: str, max_bytes: int = 5 * 1024 * 1024) -> str:
    """Small GET returning decoded text. For listing pages and JSON metadata."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=PROBE_TIMEOUT) as resp:
            data = resp.read(max_bytes + 1)
            if len(data) > max_bytes:
                raise HttpError(f"response exceeded {max_bytes} bytes")
            enc = resp.headers.get_content_charset() or "utf-8"
            return data.decode(enc, errors="replace")
    except (TimeoutError, urllib.error.HTTPError, urllib.error.URLError) as e:
        raise HttpError(f"GET {url} → {e}") from e


def download(
    url: str,
    dest: Path,
    on_progress: Callable[[int, int | None], None] | None = None,
    *,
    expected_min_bytes: int = 0,
    cancel_check: Callable[[], bool] | None = None,
) -> int:
    """Stream-download ``url`` into ``dest`` atomically.

    Writes to ``dest.with_suffix(dest.suffix + '.partial')`` and renames
    on success. Reports progress as ``on_progress(bytes_done, bytes_total)``
    where ``bytes_total`` may be ``None`` if the server didn't send
    Content-Length.

    Retries the *whole* request up to ``len(RETRY_DELAYS)`` times on
    network errors. (We don't try Range-resume across retries because it
    complicates atomicity for marginal gain — most files here are small.)

    Returns the final byte count.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".partial")

    last_err: Exception | None = None
    for attempt in range(len(RETRY_DELAYS) + 1):
        try:
            return _do_download(url, tmp, dest, on_progress, expected_min_bytes, cancel_check)
        except (TimeoutError, HttpError, urllib.error.URLError, OSError) as e:
            last_err = e
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass
            if attempt < len(RETRY_DELAYS):
                time.sleep(RETRY_DELAYS[attempt])
                continue
            break
    raise HttpError(f"download {url} failed after retries: {last_err}")


def _do_download(
    url: str,
    tmp: Path,
    dest: Path,
    on_progress: Callable[[int, int | None], None] | None,
    expected_min_bytes: int,
    cancel_check: Callable[[], bool] | None,
) -> int:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
        total: int | None = None
        cl = resp.headers.get("Content-Length")
        if cl is not None:
            try:
                total = int(cl)
            except ValueError:
                total = None

        bytes_done = 0
        with open(tmp, "wb") as f:
            while True:
                if cancel_check is not None and cancel_check():
                    raise HttpError("download cancelled by user")
                chunk = resp.read(CHUNK)
                if not chunk:
                    break
                f.write(chunk)
                bytes_done += len(chunk)
                if on_progress is not None:
                    on_progress(bytes_done, total)

    if expected_min_bytes and bytes_done < expected_min_bytes:
        raise HttpError(f"downloaded only {bytes_done} bytes, expected ≥ {expected_min_bytes}")

    os.replace(tmp, dest)
    if on_progress is not None:
        on_progress(bytes_done, total if total is not None else bytes_done)
    return bytes_done
