"""LLM-powered diagnosis of failed source verifications.

Only consulted on demand — when the hardcoded verify check in
verify_raw.py flags a FAIL row and the user clicks "Diagnose this
failure" in the puller UI. Costs a few cents per call (one Claude
Opus 4.7 request with prompt caching on the static source-signatures
context).

Requires ``ANTHROPIC_API_KEY`` in the environment. If missing, the
caller should fall back to displaying the raw verify reason.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from fetch import RAW_ROOT
from fetch.registry import get_source
from verify_raw import SIGNATURES, VerifyResult


# Anthropic SDK is optional — only import when actually diagnosing.
def _client():
    import anthropic  # noqa: WPS433 — deferred import is intentional

    return anthropic.Anthropic()


class DiagnoseUnavailable(RuntimeError):
    """Raised when the Anthropic SDK can't be reached (missing key, etc.)."""


def _build_system_prompt() -> list[dict]:
    """Static framing + every source's expected signature.

    Stays byte-stable across calls so the prefix caches effectively.
    Ends with a single ``cache_control`` breakpoint so the entire block
    is treated as one cached prefix.
    """
    sigs_text = json.dumps(
        {
            sid: {k: (sorted(v) if isinstance(v, set) else v) for k, v in sig.items()}
            for sid, sig in SIGNATURES.items()
        },
        indent=2,
        sort_keys=True,
    )
    framing = (
        "You are diagnosing why a manually-downloaded data file failed the "
        "pilot data puller's contents verification. The puller pulls public "
        "datasets (FCC ASR/ULS, HUD, NC OneMap parcels, EIA, ARC, USDA, "
        "etc.) into `data/raw/<source_id>/current/`. When a folder is "
        "wrong, it's usually because the user (a) downloaded the wrong "
        "file from the publisher's page, (b) dropped it into the wrong "
        "source folder, or (c) got a truncated download.\n\n"
        "FCC ULS files in particular share many table names (HD.dat, "
        "EN.dat, LO.dat, FR.dat, MK.dat appear across most services); "
        "service-specific markers distinguish them — LD.dat for leasing, "
        "TA.dat for transfers, underscore-prefix files for ownership, "
        "MC/MF/MP.dat for market-based services, BC/BF/F2/FF.dat for "
        "microwave, RA.dat for ASR registrations.\n\n"
        "Your job, given one failed source folder:\n"
        "  1. Diagnose the most likely cause in ONE sentence.\n"
        "  2. Recommend a concrete next step (e.g. 'download <file> from "
        "<URL> instead', 'this is the right file but partial — re-download', "
        "'this folder belongs to source X, move it').\n"
        "  3. Keep total response under 150 words. No preamble, no "
        "summary — start with the diagnosis.\n\n"
        "Here are the signatures for every source slot the puller knows "
        "about (filenames that must / should / must-not appear):\n\n"
        f"```json\n{sigs_text}\n```"
    )
    return [
        {
            "type": "text",
            "text": framing,
            "cache_control": {"type": "ephemeral"},
        }
    ]


def _gather_folder_context(
    source_id: str, max_files_listed: int = 80, max_file_samples: int = 3, sample_bytes: int = 2000
) -> dict:
    """Collect a structured snapshot of what's actually in the folder."""
    folder = RAW_ROOT / source_id / "current"
    if not folder.exists():
        return {"folder_exists": False}

    files = [f for f in folder.rglob("*") if f.is_file() and not f.is_symlink()]
    files.sort()

    total_bytes = sum(f.stat().st_size for f in files)
    listing = [
        {"path": str(f.relative_to(folder)), "size": f.stat().st_size}
        for f in files[:max_files_listed]
    ]
    truncated_listing = len(files) > max_files_listed

    # Sample a few suspicious files' headers. Prefer the smaller .dat files
    # (counts, schema, etc.) and any plausibly-textual files.
    text_candidates = [
        f
        for f in files
        if f.suffix.lower() in (".csv", ".txt", ".dat", ".json", ".xml", ".md", ".tsv")
    ]
    text_candidates.sort(key=lambda p: p.stat().st_size)
    samples = []
    for f in text_candidates[:max_file_samples]:
        try:
            with open(f, "rb") as fh:
                raw = fh.read(sample_bytes)
            samples.append(
                {
                    "path": str(f.relative_to(folder)),
                    "size": f.stat().st_size,
                    "head": raw.decode("utf-8", errors="replace"),
                }
            )
        except OSError:
            continue

    return {
        "folder_exists": True,
        "total_bytes": total_bytes,
        "file_count": len(files),
        "listing": listing,
        "listing_truncated": truncated_listing,
        "samples": samples,
    }


def _build_user_message(result: VerifyResult) -> str:
    try:
        src = get_source(result.source_id)
        src_meta = {
            "id": src.id,
            "name": src.name,
            "category": src.category,
            "description": src.description,
            "coverage": src.coverage,
        }
    except KeyError:
        src_meta = {"id": result.source_id, "name": "(unknown source — not in registry)"}

    ctx = _gather_folder_context(result.source_id)

    return (
        f"Source: {json.dumps(src_meta, indent=2)}\n\n"
        f"Verify verdict: {result.verdict}\n"
        f"Verify reason: {result.detail}\n\n"
        f"Folder contents at data/raw/{result.source_id}/current/:\n"
        f"{json.dumps(ctx, indent=2)}\n\n"
        "Diagnose and recommend a fix."
    )


def diagnose(result: VerifyResult, on_chunk: Callable[[str], None] | None = None) -> str:
    """Diagnose a single failed VerifyResult. Streams to ``on_chunk`` if given.

    Returns the full response text. Raises DiagnoseUnavailable if the
    Anthropic SDK can't reach the API (missing key, network issue, etc.).
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise DiagnoseUnavailable(
            "ANTHROPIC_API_KEY is not set. Export it in your shell "
            "(or add to ~/.zshrc) and relaunch the puller."
        )

    try:
        client = _client()
    except ImportError as e:
        raise DiagnoseUnavailable(
            "anthropic SDK not installed. Run: ./.venv/bin/python -m pip install 'anthropic>=0.40'"
        ) from e

    system = _build_system_prompt()
    user_text = _build_user_message(result)

    chunks: list[str] = []
    try:
        with client.messages.stream(
            model="claude-opus-4-7",
            max_tokens=1024,
            thinking={"type": "adaptive"},
            system=system,
            messages=[{"role": "user", "content": user_text}],
        ) as stream:
            for text in stream.text_stream:
                chunks.append(text)
                if on_chunk is not None:
                    on_chunk(text)
            final = stream.get_final_message()
        usage = final.usage
        if on_chunk is not None and usage:
            # Append a quiet usage footer so users see what the call cost.
            footer = (
                f"\n\n— input {usage.input_tokens} tokens"
                f" (cached read: {getattr(usage, 'cache_read_input_tokens', 0)},"
                f" cached write: {getattr(usage, 'cache_creation_input_tokens', 0)})"
                f", output {usage.output_tokens} tokens"
            )
            on_chunk(footer)
            chunks.append(footer)
    except Exception as e:
        raise DiagnoseUnavailable(f"{type(e).__name__}: {e}") from e

    return "".join(chunks)
