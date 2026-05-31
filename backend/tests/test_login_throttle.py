"""Login brute-force throttle (Slice 2 / #77).

Pure-unit coverage of the sliding-window failure counter with an injected
clock: it allows attempts under the limit, blocks once over it within the
window, recovers as the window rolls forward (no hard lockout), keeps keys
independent, and clears a key on a successful login.
"""

from __future__ import annotations

import pytest

from backend.app.login_throttle import LoginThrottle

from ._helpers import FakeClock

A = ("10.0.0.1", "alice")
B = ("10.0.0.2", "bob")


def _throttle(clock: FakeClock, *, max_failures: int = 3, window: float = 60.0) -> LoginThrottle:
    return LoginThrottle(max_failures=max_failures, window_seconds=window, clock=clock)


def test_allows_attempts_under_the_limit() -> None:
    t = _throttle(FakeClock())
    for _ in range(2):  # limit is 3
        assert not t.is_blocked(A)
        t.record_failure(A)
    assert not t.is_blocked(A)  # 2 failures < 3


def test_blocks_once_over_the_limit_within_window() -> None:
    t = _throttle(FakeClock())
    for _ in range(3):
        assert not t.is_blocked(A)
        t.record_failure(A)
    assert t.is_blocked(A)  # 3 failures == limit → blocked


def test_block_clears_after_the_window() -> None:
    clock = FakeClock()
    t = _throttle(clock)
    for _ in range(3):
        t.record_failure(A)
    assert t.is_blocked(A)
    clock.advance(60.1)  # all three failures age out of the window
    assert not t.is_blocked(A)  # no hard lockout — the key recovers


def test_window_is_sliding_not_fixed() -> None:
    clock = FakeClock()
    t = _throttle(clock)
    t.record_failure(A)  # t=1000
    clock.advance(40)
    t.record_failure(A)  # t=1040
    clock.advance(21)  # t=1061: the first failure (1000) is now >60s old
    assert not t.is_blocked(A)  # only {1040} remains in-window → under limit
    t.record_failure(A)  # in-window: {1040, 1061}
    assert not t.is_blocked(A)  # still 2 < 3
    t.record_failure(A)  # in-window: {1040, 1061, 1061}
    assert t.is_blocked(A)


def test_keys_are_independent() -> None:
    t = _throttle(FakeClock())
    for _ in range(3):
        t.record_failure(A)
    assert t.is_blocked(A)
    assert not t.is_blocked(B)  # B is untouched by A's failures


def test_success_resets_a_key() -> None:
    t = _throttle(FakeClock())
    for _ in range(2):
        t.record_failure(A)
    t.reset(A)  # a correct password clears the counter
    t.record_failure(A)
    assert not t.is_blocked(A)  # only the post-reset failure counts


def test_retry_after_is_zero_when_not_blocked() -> None:
    t = _throttle(FakeClock())
    t.record_failure(A)
    assert t.retry_after(A) == 0.0


def test_retry_after_counts_down_to_unblock() -> None:
    clock = FakeClock()
    t = _throttle(clock)
    for _ in range(3):
        t.record_failure(A)  # all at t=1000
    assert t.retry_after(A) == 60.0  # blocked until the oldest (1000) exits at 1060
    clock.advance(10)
    assert t.retry_after(A) == 50.0


def test_clear_drops_all_state() -> None:
    t = _throttle(FakeClock())
    for _ in range(3):
        t.record_failure(A)
    assert t.is_blocked(A)
    t.clear()
    assert not t.is_blocked(A)


def test_constructor_rejects_bad_config() -> None:
    with pytest.raises(ValueError):
        LoginThrottle(max_failures=0, window_seconds=60)
    with pytest.raises(ValueError):
        LoginThrottle(max_failures=3, window_seconds=0)
