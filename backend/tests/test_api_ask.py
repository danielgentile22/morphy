"""The POST /api/audit/ask SSE route (PRD #187 / #188).

API-level behavior: it authorizes through the same session seam as the rest of
the app (unauthenticated → 401), self-disables with a clean 503 when no key is
configured (catalog unaffected), streams SSE deltas when configured, and a light
per-user throttle rejects excess requests cleanly. The Anthropic seam is faked
via a dependency override, so these never touch the network or need a key.
"""

from __future__ import annotations

from collections.abc import Iterator

from backend.app import main
from backend.app.ask_client import AnthropicNotConfigured, AnthropicStreamError

from ._helpers import api, auth_header, login

SAMPLE = {"schema_version": 1, "count": 0, "owners": []}


class _FakeStreamer:
    """Duck-types AnthropicStreamer for the route: ``ensure_ready`` + ``stream``."""

    def __init__(
        self,
        *,
        deltas: list[str] | None = None,
        configured: bool = True,
        raise_mid: bool = False,
    ) -> None:
        self._deltas = deltas or []
        self._configured = configured
        self._raise_mid = raise_mid
        self.calls: list[dict] = []  # records each stream() invocation's prompt

    def ensure_ready(self) -> None:
        if not self._configured:
            raise AnthropicNotConfigured("no key")

    def stream(self, *, system: str, messages: list[dict]) -> Iterator[str]:
        self.calls.append({"system": system, "messages": messages})
        yield from self._deltas
        if self._raise_mid:
            raise AnthropicStreamError("upstream boom")


def _use_streamer(streamer: _FakeStreamer) -> None:
    main.app.dependency_overrides[main.get_ask_streamer] = lambda: streamer


def test_unauthenticated_request_is_401() -> None:
    with api(SAMPLE) as (client, _eng, _sender):
        # No override needed — auth is checked while resolving dependencies,
        # before the body runs.
        assert client.post("/api/audit/ask", json={"question": "hi"}).status_code == 401


def test_unconfigured_key_is_a_clean_503_and_catalog_still_works() -> None:
    with api(SAMPLE) as (client, _eng, _sender):
        _use_streamer(_FakeStreamer(configured=False))
        token = login(client)
        r = client.post("/api/audit/ask", json={"question": "hi"}, headers=auth_header(token))
        assert r.status_code == 503
        assert "not configured" in r.json()["detail"].lower()
        # The rest of the catalog is unaffected by the AI being off.
        assert client.get("/api/health").status_code == 200


def test_configured_request_streams_sse_deltas() -> None:
    with api(SAMPLE) as (client, _eng, _sender):
        _use_streamer(_FakeStreamer(deltas=["Hel", "lo", "!"]))
        token = login(client)
        r = client.post(
            "/api/audit/ask", json={"question": "explain ASR"}, headers=auth_header(token)
        )
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        body = r.text
        # Deltas arrive as JSON-encoded SSE frames, in order, then a terminal done.
        assert 'event: delta\ndata: {"text": "Hel"}' in body
        assert body.index("Hel") < body.index("lo") < body.index("!")
        assert "event: done" in body


def test_mid_stream_sdk_error_degrades_to_an_error_event_not_a_500() -> None:
    with api(SAMPLE) as (client, _eng, _sender):
        _use_streamer(_FakeStreamer(deltas=["partial"], raise_mid=True))
        token = login(client)
        r = client.post("/api/audit/ask", json={"question": "hi"}, headers=auth_header(token))
        # The 200 is already committed when the stream fails — it can't become a
        # 500; it degrades to a clean error frame.
        assert r.status_code == 200
        assert "event: error" in r.text


def test_empty_question_is_rejected_by_validation() -> None:
    with api(SAMPLE) as (client, _eng, _sender):
        _use_streamer(_FakeStreamer(deltas=["x"]))
        token = login(client)
        r = client.post("/api/audit/ask", json={"question": ""}, headers=auth_header(token))
        assert r.status_code == 422


def test_grounded_payload_is_folded_into_the_prompt() -> None:
    # The route maps the request's page grounding (#189) onto the assembler:
    # prior thread → leading turns, selection/signals/page → the current turn.
    with api(SAMPLE) as (client, _eng, _sender):
        streamer = _FakeStreamer(deltas=["ok"])
        _use_streamer(streamer)
        token = login(client)
        body = {
            "question": "why is this high confidence?",
            "route": "Signal: owner_name@12",
            "selection": "owner_name",
            "visible_text": "some visible page text",
            "signals": [
                {
                    "id": "owner_name@12",
                    "confidence": "high",
                    "upstream_origin": "official_filing",
                    "freshness_risk": "low",
                    "derivation_risk": "low",
                    "verifiability": "high",
                    "verdict": "Authoritative.",
                }
            ],
            "thread": [
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "hello"},
            ],
        }
        r = client.post("/api/audit/ask", json=body, headers=auth_header(token))
        assert r.status_code == 200
        assert len(streamer.calls) == 1
        messages = streamer.calls[0]["messages"]
        # Two prior turns, then the grounded current question.
        assert [m["role"] for m in messages] == ["user", "assistant", "user"]
        grounded = messages[-1]["content"]
        assert "owner_name@12" in grounded
        assert "confidence=high" in grounded
        assert "owner_name" in grounded  # the selection
        assert grounded.rstrip().endswith("Question: why is this high confidence?")


def test_per_user_rate_limit_rejects_excess_requests() -> None:
    with api(SAMPLE) as (client, _eng, _sender):
        _use_streamer(_FakeStreamer(deltas=["ok"]))
        # One shared throttle, one request per window — the override must return
        # the *same* instance each request so its sliding window accumulates.
        throttle = main.LoginThrottle(max_failures=1, window_seconds=300)
        main.app.dependency_overrides[main.get_ask_throttle] = lambda: throttle
        token = login(client)
        first = client.post("/api/audit/ask", json={"question": "q1"}, headers=auth_header(token))
        assert first.status_code == 200
        second = client.post("/api/audit/ask", json={"question": "q2"}, headers=auth_header(token))
        assert second.status_code == 429
        assert "Retry-After" in second.headers
