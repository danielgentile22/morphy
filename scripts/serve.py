"""Range-capable static file server for the map app's data.

`python -m http.server` does **not** honour HTTP `Range` requests — it
answers every request with `200 OK` and the full body. The map app needs
`Range` / `206 Partial Content` so PMTiles (vector tiles) and DuckDB-WASM
(parquet) can fetch byte ranges instead of downloading whole
multi-hundred-MB files. This server adds that.

Usage::

    python scripts/serve.py [port] [--directory DIR]

Serves the repo root (or ``DIR``) on ``port`` (default 8765). Use it in
place of ``python -m http.server`` for both the Vite dev proxy upstream
and the single-origin demo server.
"""

from __future__ import annotations

import argparse
import os
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

_COPY_CHUNK = 64 * 1024


def _parse_byte_range(header: str, size: int) -> tuple[int, int]:
    """Parse a single ``bytes=`` range into inclusive (start, end).

    Raises ValueError for an unsupported or unsatisfiable range.
    """
    if not header.startswith("bytes="):
        raise ValueError("unsupported range unit")
    spec = header[len("bytes=") :].split(",")[0].strip()
    first, sep, last = spec.partition("-")
    if not sep:
        raise ValueError("malformed range")
    if first == "":  # suffix range: bytes=-N (final N bytes)
        n = int(last)
        if n <= 0:
            raise ValueError("malformed suffix range")
        return max(0, size - n), size - 1
    start = int(first)
    end = int(last) if last else size - 1
    end = min(end, size - 1)
    if start > end or start >= size:
        raise ValueError("unsatisfiable range")
    return start, end


class RangeHandler(SimpleHTTPRequestHandler):
    """``SimpleHTTPRequestHandler`` + single-range HTTP ``Range`` support."""

    # How many bytes the current response body should still emit; None
    # means "no range — copy the whole file" (the base-class behaviour).
    _range_remaining: int | None = None

    def end_headers(self) -> None:
        # Advertise range support on every response so range-aware
        # clients (DuckDB-WASM HEADs the file first) know to use it.
        self.send_header("Accept-Ranges", "bytes")
        super().end_headers()

    def copyfile(self, source, outputfile) -> None:  # type: ignore[no-untyped-def]
        if self._range_remaining is None:
            super().copyfile(source, outputfile)
            return
        remaining = self._range_remaining
        while remaining > 0:
            chunk = source.read(min(_COPY_CHUNK, remaining))
            if not chunk:
                break
            outputfile.write(chunk)
            remaining -= len(chunk)

    def send_head(self):  # type: ignore[no-untyped-def]
        self._range_remaining = None
        rng = self.headers.get("Range")
        if not rng:
            return super().send_head()

        path = self.translate_path(self.path)
        if not os.path.isfile(path):
            # Directories / missing files — fall back to default handling.
            return super().send_head()

        size = os.path.getsize(path)
        try:
            start, end = _parse_byte_range(rng, size)
        except ValueError:
            self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
            self.send_header("Content-Range", f"bytes */{size}")
            self.end_headers()
            return None

        f = open(path, "rb")
        f.seek(start)
        self._range_remaining = end - start + 1
        self.send_response(HTTPStatus.PARTIAL_CONTENT)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        return f


def main() -> int:
    parser = argparse.ArgumentParser(description="Range-capable static file server.")
    parser.add_argument("port", nargs="?", type=int, default=8765, help="port (default 8765)")
    parser.add_argument(
        "--directory",
        default=str(Path(__file__).resolve().parent.parent),
        help="directory to serve (default: repo root)",
    )
    args = parser.parse_args()

    handler = partial(RangeHandler, directory=args.directory)
    with ThreadingHTTPServer(("", args.port), handler) as httpd:
        print(f"Serving {args.directory} on http://localhost:{args.port} (Range-capable)")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
