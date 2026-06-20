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
    AskUsage,
)


class _Usage:
    def __init__(self, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class _FinalMessage:
    def __init__(self, usage: _Usage) -> None:
        self.usage = usage


class _FakeStream:
    """Stands in for the SDK's streaming context manager. Optionally exposes a
    final message with usage (mirrors the real SDK's ``get_final_message``)."""

    def __init__(self, deltas: list[str], usage: _Usage | None = None) -> None:
        self._deltas = deltas
        self._usage = usage

    def __enter__(self) -> _FakeStream:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    @property
    def text_stream(self):
        yield from self._deltas

    def get_final_message(self) -> _FinalMessage:
        if self._usage is None:
            raise AttributeError("no final message")  # a stream without usage
        return _FinalMessage(self._usage)


class _FakeMessages:
    def __init__(
        self,
        *,
        deltas: list[str] | None = None,
        error: Exception | None = None,
        usage: _Usage | None = None,
    ) -> None:
        self._deltas = deltas or []
        self._error = error
        self._usage = usage
        self.calls: list[dict] = []

    def stream(self, **kwargs):
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return _FakeStream(self._deltas, self._usage)


class _FakeClient:
    def __init__(
        self,
        *,
        deltas: list[str] | None = None,
        error: Exception | None = None,
        usage: _Usage | None = None,
    ) -> None:
        self.messages = _FakeMessages(deltas=deltas, error=error, usage=usage)


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


def test_usage_is_captured_after_a_completed_stream() -> None:
    # The route persists token usage with the Q&A (#190); the streamer pulls it
    # from the final message once the text_stream is drained.
    client = _FakeClient(deltas=["Hi"], usage=_Usage(123, 45))
    streamer = _streamer(client=client)
    assert streamer.usage is None  # nothing captured before streaming
    list(streamer.stream(system="s", messages=[{"role": "user", "content": "hi"}]))
    assert streamer.usage == AskUsage(input_tokens=123, output_tokens=45)


def test_usage_is_none_when_the_stream_exposes_no_final_message() -> None:
    # Best-effort: a stream without usage (older SDK, a fake) leaves it None
    # rather than breaking the answer.
    client = _FakeClient(deltas=["Hi"])  # no usage
    streamer = _streamer(client=client)
    list(streamer.stream(system="s", messages=[{"role": "user", "content": "hi"}]))
    assert streamer.usage is None
