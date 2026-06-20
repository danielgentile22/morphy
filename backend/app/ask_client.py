"""The Anthropic streaming client wrapper for "Ask Claude" (PRD #187 / #188).

The single I/O seam between the app and the Anthropic SDK: an assembled prompt
goes in, ordered text deltas come out. It exists so the route never touches the
SDK directly and so tests can fake the whole thing — no network, no key.

Two failure modes are made *typed* so the route can map each to a clean HTTP
response instead of leaking a 500 stack (PRD: "the site still works if AI is
down"):

- ``AnthropicNotConfigured`` — no ``ANTHROPIC_API_KEY``. Surfaced *before*
  streaming begins (``ensure_ready``) so the route can answer a clean 503.
- ``AnthropicStreamError`` — any SDK / network / API error during streaming,
  mapped from the raw SDK exception so the caller sees one stable type.

The ``anthropic`` SDK is imported lazily inside the wrapper, so importing this
module (and the FastAPI app, for the OpenAPI export) never requires the SDK or
a key.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AskUsage:
    """Token usage for one completed stream — captured best-effort for cost
    review (#190). ``None`` on the streamer when the SDK never surfaced a final
    message (mid-stream failure, or a fake without usage)."""

    input_tokens: int
    output_tokens: int


def _extract_usage(stream: Any) -> AskUsage | None:
    """Pull token usage from a finished SDK stream, defensively. Returns
    ``None`` for any stream that doesn't expose a final message with usage (a
    test fake, an SDK version without it) — usage is a nice-to-have, never a
    reason to break the answer the user already saw."""
    try:
        usage = stream.get_final_message().usage
        return AskUsage(int(usage.input_tokens), int(usage.output_tokens))
    except Exception:  # noqa: BLE001 — usage is best-effort; never raise from here
        return None


class AnthropicNotConfigured(RuntimeError):
    """No API key is configured. The route maps this to a 503 'not configured'
    and the rest of the catalog is unaffected."""


class AnthropicStreamError(RuntimeError):
    """An SDK / network / API error while streaming, mapped from the raw SDK
    exception. The route surfaces it as a clean error event, never a 500."""


class AnthropicStreamer:
    """Streams text deltas for an assembled prompt.

    The live client is created lazily from ``api_key``; tests inject a fake via
    ``client`` (any object exposing ``messages.stream(...)`` as a context
    manager yielding ``.text_stream``), which also bypasses the key check.
    """

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        max_tokens: int,
        client: Any | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._max_tokens = max_tokens
        self._client = client
        # Populated after a stream finishes (best-effort) so the route can log
        # token usage with the persisted Q&A (#190). A fresh streamer is built
        # per request, so this per-instance field carries no cross-request state.
        self.usage: AskUsage | None = None

    @property
    def model(self) -> str:
        """The model this streamer answers with — persisted with each Q&A."""
        return self._model

    def ensure_ready(self) -> None:
        """Raise ``AnthropicNotConfigured`` if the helper can't run (no key and
        no injected client). Called by the route before it commits to a 200 SSE
        response, so 'not configured' is a clean 503 rather than a broken
        stream."""
        self._get_client()

    def stream(self, *, system: str, messages: list[dict[str, str]]) -> Iterator[str]:
        """Yield the answer's text deltas in order.

        Raises ``AnthropicNotConfigured`` if unconfigured (the route guards this
        with ``ensure_ready`` first) and ``AnthropicStreamError`` for any SDK
        failure — never the raw SDK exception.
        """
        client = self._get_client()
        try:
            with client.messages.stream(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system,
                messages=messages,
            ) as stream:
                yield from stream.text_stream
                # The text_stream is drained; the final message (with usage) is
                # now available. Captured here, inside the `with`, before exit.
                self.usage = _extract_usage(stream)
        except AnthropicNotConfigured:
            raise
        except Exception as exc:  # noqa: BLE001 — map *any* SDK/network error to our type
            raise AnthropicStreamError(str(exc)) from exc

    def _get_client(self) -> Any:
        if self._client is None:
            if not self._api_key:
                raise AnthropicNotConfigured("ANTHROPIC_API_KEY is not set")
            # Lazy import so this module + the FastAPI app import without the SDK
            # (e.g. the OpenAPI export runs in a slim env).
            import anthropic

            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client
