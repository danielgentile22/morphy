"""In-process brute-force throttle for the login route (Slice 2 / #77).

A sliding-window failure counter keyed by ``(ip, username)``. After
``max_failures`` failed sign-ins for one key inside ``window_seconds``,
further attempts are rejected until the oldest in-window failure ages out and
the count falls back under the limit — there is **no hard lockout**. Because
the IP is part of the key and the block self-clears, an attacker who knows a
username can't use it to permanently lock a real user out (no lockout-DoS).

State is per-process (acceptable on the single VM; it resets on restart). The
clock is injectable so tests drive time deterministically; the default is
``time.monotonic`` (immune to wall-clock adjustments). Memory is bounded by an
opportunistic sweep that drops fully-expired keys, so failure spray across many
distinct keys can't grow the map without bound.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Callable

Key = tuple[str, str]


class LoginThrottle:
    # Sweep expired keys every Nth recorded failure — cheap amortized cleanup so
    # spray across many (ip, username) keys can't accumulate empty/stale buckets.
    _SWEEP_EVERY = 256

    def __init__(
        self,
        *,
        max_failures: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_failures < 1:
            raise ValueError("max_failures must be >= 1")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be > 0")
        self._max = max_failures
        self._window = window_seconds
        self._clock = clock
        self._failures: dict[Key, deque[float]] = defaultdict(deque)
        self._ops = 0

    def is_blocked(self, key: Key) -> bool:
        """True if ``key`` has ``>= max_failures`` failures inside the window."""
        return self._recent(key) >= self._max

    def record_failure(self, key: Key) -> None:
        """Note a failed attempt for ``key`` at the current time."""
        self._failures[key].append(self._clock())
        self._maybe_sweep()

    def reset(self, key: Key) -> None:
        """Clear a key's failures — called on a successful login."""
        self._failures.pop(key, None)

    def retry_after(self, key: Key) -> float:
        """Seconds until ``key`` clears (0.0 when it isn't currently blocked).

        Once blocked, the key frees up when its oldest in-window failure exits
        the window, dropping the count back under the limit."""
        if self._recent(key) < self._max:  # prunes expired entries as a side effect
            return 0.0
        oldest = self._failures[key][0]
        return max(0.0, self._window - (self._clock() - oldest))

    def clear(self) -> None:
        """Drop all state (test isolation)."""
        self._failures.clear()
        self._ops = 0

    def _recent(self, key: Key) -> int:
        """Count this key's failures within the window, pruning older ones; drop
        the bucket entirely once it empties so absent keys stay absent."""
        bucket = self._failures.get(key)
        if bucket is None:
            return 0
        cutoff = self._clock() - self._window
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        if not bucket:
            del self._failures[key]
            return 0
        return len(bucket)

    def _maybe_sweep(self) -> None:
        """Periodically discard keys whose failures have all aged out."""
        self._ops += 1
        if self._ops % self._SWEEP_EVERY:
            return
        cutoff = self._clock() - self._window
        for key in list(self._failures):
            bucket = self._failures[key]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if not bucket:
                del self._failures[key]
