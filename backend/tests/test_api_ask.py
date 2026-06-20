"""The POST /api/audit/ask SSE route (PRD #187 / #188).

API-level behavior: it authorizes through the same session seam as the rest of
the app (unauthenticated → 401), self-disables with a clean 503 when no key is
configured (catalog unaffected), streams SSE deltas when configured, and a light
per-user throttle rejects excess requests cleanly. The Anthropic seam is faked
via a dependency override, so these never touch the network or need a key.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from backend.app import main
from backend.app.ask_client import AnthropicNotConfigured, AnthropicStreamError, AskUsage
from backend.app.ask_log_store import AskLogStore

from ._helpers import api, auth_header, login

SAMPLE = {"schema_version": 1, "count": 0, "owners": []}


def _logs(eng: Engine, tenant_id: int = 1) -> list:
    """The persisted Q&A rows for a tenant (dev → tenant 1), read straight from
    the test engine — the slice-3 (#190) storage assertion."""
    return AskLogStore(Session(bind=eng, future=True), tenant_id).list()


class _FakeStreamer:
    """Duck-types AnthropicStreamer for the route: ``ensure_ready`` + ``stream``,
    plus ``model`` + ``usage`` (read by the persistence path, #190)."""

    def __init__(
        self,
        *,
        deltas: list[str] | None = None,
        configured: bool = True,
        raise_mid: bool = False,
        usage: AskUsage | None = None,
    ) -> None:
        self._deltas = deltas or []
        self._configured = configured
        self._raise_mid = raise_mid
        self.model = "fake-model"
        self.usage = usage
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


def test_completed_qa_is_persisted_with_its_context_snapshot() -> None:
    # Slice 3 (#190): a completed stream writes one tenant-scoped row capturing
    # the answer + the context that was on screen + model + usage.
    with api(SAMPLE) as (client, eng, _sender):
        _use_streamer(_FakeStreamer(deltas=["The ", "answer."], usage=AskUsage(100, 20)))
        token = login(client)
        body = {
            "question": "why is this high confidence?",
            "route": "Signal: owner_name@12",
            "selection": "owner_name",
            "visible_text": "some visible page text",
            "signals": [
                {"id": "owner_name@12", "confidence": "high"},
                {"id": "foo@05", "confidence": "low"},
            ],
            "thread": [],
        }
        r = client.post("/api/audit/ask", json=body, headers=auth_header(token))
        assert r.status_code == 200
        assert "event: done" in r.text  # the stream finished cleanly

        rows = _logs(eng)
        assert len(rows) == 1
        row = rows[0]
        assert row.question == "why is this high confidence?"
        assert row.answer == "The answer."  # the streamed deltas, reassembled
        assert row.route == "Signal: owner_name@12"
        assert row.selection == "owner_name"
        assert row.signal_ids == "owner_name@12,foo@05"  # the on-screen ids
        assert row.model == "fake-model"
        assert (row.input_tokens, row.output_tokens) == (100, 20)
        assert row.username == "dev"  # the asker (the JWT subject)


def test_a_failed_stream_persists_nothing() -> None:
    # A mid-stream SDK failure is not a completed Q&A — nothing is stored.
    with api(SAMPLE) as (client, eng, _sender):
        _use_streamer(_FakeStreamer(deltas=["partial"], raise_mid=True))
        token = login(client)
        r = client.post("/api/audit/ask", json={"question": "hi"}, headers=auth_header(token))
        assert r.status_code == 200
        assert "event: error" in r.text
        assert _logs(eng) == []


def test_persisted_qa_is_tenant_scoped() -> None:
    # Two teams ask; each team's stored Q&A is invisible to the other (#190).
    with api(SAMPLE) as (client, eng, _sender):
        _use_streamer(_FakeStreamer(deltas=["a"]))
        from ._helpers import temp_credential

        dev = login(client)  # dev → tenant 1
        client.post("/api/audit/ask", json={"question": "team-1 q"}, headers=auth_header(dev))
        with temp_credential(eng, "u2", "pw2", team="otherteam"):
            other = login(client, "u2", "pw2")  # otherteam → tenant 2
            client.post(
                "/api/audit/ask", json={"question": "team-2 q"}, headers=auth_header(other)
            )

        # Tenant 1 (devteam) sees only its own; tenant 2 only its own.
        assert [r.question for r in _logs(eng, 1)] == ["team-1 q"]
        assert [r.question for r in _logs(eng, 2)] == ["team-2 q"]


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
