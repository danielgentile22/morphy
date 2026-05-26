"""Legacy entry point for interestingness scoring.

The real implementation now lives in two modules per ADR-058:
- `score_components` — pure weight-free signal extraction
- `score_weights` — `ScoringProfile` + `apply_weights`

`score_parcel_row` is preserved as a thin wrapper for external callers
that imported it directly. New code should call `compute_components` +
`apply_weights` so it can plug in a non-default profile.
"""

from __future__ import annotations

from typing import Any

from .score_components import ScoreComponents, compute_components
from .score_weights import DEFAULT_PROFILE, ScoringProfile, apply_weights

__all__ = [
    "ScoreComponents",
    "ScoringProfile",
    "DEFAULT_PROFILE",
    "compute_components",
    "apply_weights",
    "score_parcel_row",
]


def score_parcel_row(row: Any) -> tuple[float, dict[str, float]]:
    """Compute (score, post-weight components dict) for a parcel row.

    Default-profile convenience wrapper preserved for backwards
    compatibility — composes `compute_components` + `apply_weights`.
    Returns the same `(score, breakdown)` shape callers expected.
    """
    return apply_weights(compute_components(row), DEFAULT_PROFILE)
