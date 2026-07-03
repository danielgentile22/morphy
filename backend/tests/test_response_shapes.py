"""Round-trip tests for the collapsed Out schemas (#256, PRD #253 W2).

Each collapsed entity validates straight from its source object (ORM row,
service dataclass, or store) into its Out schema; these pin that no field is
dropped and that the wire-shape transforms (ISO dates, labels list, config
JSON) match what the deleted hand mappers produced.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy.orm import Session

from backend.app.activity_service import ActivityEvent
from backend.app.attention_service import AttentionItem
from backend.app.models import AntennaOverride, ScoringPreset, Task, User
from backend.app.schemas import (
    ActivityEventOut,
    AntennaState,
    AttentionItemOut,
    LeadDetail,
    ScoringPresetOut,
    SettingsResponse,
    StatsResponse,
    TaskOut,
    UserOut,
)
from backend.app.settings_store import SettingsStore
from backend.app.stats_service import StatsResult


def test_task_row_roundtrip(engine) -> None:
    with Session(bind=engine) as s:
        task = Task(
            tenant_id=1,
            title="call",
            description="desc",
            status="done",
            priority="high",
            due_date=date(2026, 7, 1),
            assignee_user_id=7,
            lead_cluster_id="cid1",
            tower_asr="1234567",
            labels="dev,outreach",
            source="auto",
            created_by_user_id=3,
            completed_at=datetime(2026, 7, 2, 12, 0, tzinfo=UTC),
        )
        s.add(task)
        s.commit()
        out = TaskOut.model_validate(task)
    assert out.model_dump() == {
        "id": task.id,
        "title": "call",
        "description": "desc",
        "status": "done",
        "priority": "high",
        "due_date": "2026-07-01",
        "assignee_user_id": 7,
        "lead_cluster_id": "cid1",
        "tower_asr": "1234567",
        "labels": ["dev", "outreach"],
        "source": "auto",
        "created_by_user_id": 3,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
        # isoformat of whatever the driver returns (SQLite reads back naive) —
        # identical to what the deleted hand mapper produced.
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
    }


def test_task_row_roundtrip_unset_optionals(engine) -> None:
    with Session(bind=engine) as s:
        task = Task(tenant_id=1, title="bare")
        s.add(task)
        s.commit()
        out = TaskOut.model_validate(task)
    assert out.due_date is None and out.completed_at is None
    assert out.labels == []


def test_antenna_row_roundtrip(engine) -> None:
    row = AntennaOverride(
        tenant_id=1,
        asr="1234567",
        archived=True,
        address="1 Main St",
        owner_name="Jane",
        owner_phone="555",
        owner_email="j@x.test",
        notes="n",
    )
    out = AntennaState.model_validate(row)
    assert out.model_dump() == {
        "asr": "1234567",
        "archived": True,
        "address": "1 Main St",
        "owner_name": "Jane",
        "owner_phone": "555",
        "owner_email": "j@x.test",
        "notes": "n",
    }


def test_scoring_preset_roundtrip_decodes_config() -> None:
    row = ScoringPreset(tenant_id=1, name="w", config='{"useDefault": false}', is_default=True)
    row.id = 5
    out = ScoringPresetOut.model_validate(row)
    assert out.model_dump() == {
        "id": 5,
        "name": "w",
        "config": {"useDefault": False},
        "is_default": True,
    }


def test_scoring_preset_garbage_config_serves_empty_dict() -> None:
    row = ScoringPreset(tenant_id=1, name="w", config="not-json", is_default=False)
    row.id = 6
    assert ScoringPresetOut.model_validate(row).config == {}


def test_user_roundtrip_name_fallback() -> None:
    named = User(tenant_id=1, email="a@x.test", display_name="Alice")
    named.id = 1
    unnamed = User(tenant_id=1, email="b@x.test", display_name="")
    unnamed.id = 2
    assert UserOut.model_validate(named).name == "Alice"
    out = UserOut.model_validate(unnamed)
    assert (out.name, out.display_name, out.email) == ("b@x.test", "", "b@x.test")


def test_attention_item_roundtrip() -> None:
    item = AttentionItem(
        kind="reply", title="t", when="2026-07-01", cluster_id="c", owner_name="o", task_id=9
    )
    assert AttentionItemOut.model_validate(item).model_dump() == {
        "kind": "reply",
        "title": "t",
        "when": "2026-07-01",
        "cluster_id": "c",
        "owner_name": "o",
        "task_id": 9,
    }


def test_activity_event_roundtrip() -> None:
    ev = ActivityEvent(
        id=1,
        date="2026-07-01",
        kind="touch",
        channel="call",
        cluster_id="c",
        owner_name="o",
        logged_by_user_id=2,
        member_name="Alice",
        summary="s",
    )
    out = ActivityEventOut.model_validate(ev)
    assert out.model_dump() == {
        "id": 1,
        "date": "2026-07-01",
        "kind": "touch",
        "channel": "call",
        "cluster_id": "c",
        "owner_name": "o",
        "logged_by_user_id": 2,
        "member_name": "Alice",
        "summary": "s",
    }


def test_stats_result_roundtrip() -> None:
    r = StatsResult(
        funnel={"new": 1},
        conversion={"contacted": 0.5},
        reply_rate=0.25,
        win_rate=0.1,
        volume_by_channel={"call": 2},
        activity_total=2,
        active_days=1,
        by_state={"AR": {"new": 1}},
        by_member={"Alice": 2},
    )
    assert StatsResponse.model_validate(r).model_dump() == {
        "funnel": {"new": 1},
        "conversion": {"contacted": 0.5},
        "reply_rate": 0.25,
        "win_rate": 0.1,
        "volume_by_channel": {"call": 2},
        "activity_total": 2,
        "active_days": 1,
        "by_state": {"AR": {"new": 1}},
        "by_member": {"Alice": 2},
    }


def test_lead_view_dict_validates_into_lead_detail() -> None:
    # The shape owners_index_service.lead_view returns — owner carries the
    # lead status, so no per-field mapper sits between the view and the schema.
    view = {
        "owner": {
            "display_cluster_id": "c1",
            "owner_name": "ACME",
            "owner_kind": "llc",
            "states": ["AR"],
            "n_states": 1,
            "cross_state": False,
            "parcel_count": 1,
            "tower_count": 1,
            "solar_count": 0,
            "total_assessed_value": 1.0,
            "max_parcel_score": 0.5,
            "score": 0.5,
            "distress_tier": "at-risk",
            "in_oz": False,
            "in_qct": False,
            "persistent_poverty": False,
            "trigger_asr": "1234567",
            "status": "researching",
        },
        "status": "researching",
        "notes": "n",
        "updated_at": "2026-07-01T00:00:00",
        "attempts": [
            {
                "id": 1,
                "occurred_on": "2026-07-01",
                "channel": "call",
                "outcome": "",
                "note": "",
                "direction": "outbound",
            }
        ],
        "contact_name": "Jane",
        "contact_phone": "",
        "contact_email": "",
        "best_channel": "",
        "mailing_address": {"addr": "1 Main", "city": "X", "state": "AR", "zip": "72201"},
        "tallest_tower_height_m": 30.5,
        "holdings": [],
        "merged_members": [{"display_cluster_id": "c2", "owner_name": "ACME 2"}],
    }
    detail = LeadDetail.model_validate(view)
    assert detail.owner.status == "researching"
    assert detail.owner.trigger_asr == "1234567"
    assert [a.channel for a in detail.attempts] == ["call"]
    assert detail.merged_members[0].display_cluster_id == "c2"
    assert detail.mailing_address is not None and detail.mailing_address.zip == "72201"


def test_settings_store_roundtrip(engine) -> None:
    store = SettingsStore(Session(bind=engine), tenant_id=1)
    out = SettingsResponse.model_validate(store)
    assert out.model_dump() == {
        "auto_followup_enabled": True,
        "auto_followup_window_days": 90,
    }
