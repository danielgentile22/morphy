"""The Anthropic streaming client wrapper (PRD #188).

The seam is faked end-to-end — no network, no key. The contract under test is
the "site still works if AI is down" promise: a missing key is a typed
*not configured* condition, an SDK error is mapped to one stable type (never a
raw 500), and deltas come out in order.
"""

from __future__ import annotations

import pytest

from backend.app.ask_client import (
    AnthropicNotConfigured,
    AnthropicStreamer,
    AnthropicStreamError,
)


class _FakeStream:
    """Stands in for the SDK's streaming context manager."""

    def __init__(self, deltas: list[str]) -> None:
        self._deltas = deltas

    def __enter__(self) -> _FakeStream:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    @property
    def text_stream(self):
        yield from self._deltas


class _FakeMessages:
    def __init__(self, *, deltas: list[str] | None = None, error: Exception | None = None) -> None:
        self._deltas = deltas or []
        self._error = error
        self.calls: list[dict] = []

    def stream(self, **kwargs):
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return _FakeStream(self._deltas)


class _FakeClient:
    def __init__(self, *, deltas: list[str] | None = None, error: Exception | None = None) -> None:
        self.messages = _FakeMessages(deltas=deltas, error=error)


def _streamer(**kw) -> AnthropicStreamer:
    return AnthropicStreamer(api_key=None, model="test-model", max_tokens=64, **kw)


def test_no_key_is_a_typed_not_configured_condition() -> None:
    # No key and no injected client → the route turns this into a clean 503.
    streamer = AnthropicStreamer(api_key=None, model="m", max_tokens=10)
    with pytest.raises(AnthropicNotConfigured):
        streamer.ensure_ready()
    with pytest.raises(AnthropicNotConfigured):
        list(streamer.stream(system="s", messages=[{"role": "user", "content": "hi"}]))


def test_deltas_are_yielded_in_order() -> None:
    client = _FakeClient(deltas=["Hel", "lo", ", world"])
    streamer = _streamer(client=client)
    streamer.ensure_ready()  # an injected client is "configured"
    out = list(streamer.stream(system="sys", messages=[{"role": "user", "content": "hi"}]))
    assert out == ["Hel", "lo", ", world"]
    # The assembled prompt is handed straight to the SDK call.
    assert client.messages.calls[0]["system"] == "sys"
    assert client.messages.calls[0]["model"] == "test-model"
    assert client.messages.calls[0]["max_tokens"] == 64


def test_sdk_error_is_mapped_not_a_raw_500() -> None:
    client = _FakeClient(error=RuntimeError("upstream 529 overloaded"))
    streamer = _streamer(client=client)
    with pytest.raises(AnthropicStreamError):
        list(streamer.stream(system="s", messages=[{"role": "user", "content": "hi"}]))
