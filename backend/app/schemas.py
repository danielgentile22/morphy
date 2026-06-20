"""Pydantic request/response models for the thin Lead REST surface."""

from __future__ import annotations

from pydantic import BaseModel, Field


class OwnerSummary(BaseModel):
    display_cluster_id: str
    owner_name: str
    owner_kind: str
    states: list[str]
    n_states: int
    cross_state: bool
    parcel_count: int
    tower_count: int
    solar_count: int
    total_assessed_value: float
    max_parcel_score: float
    score: float
    distress_tier: str
    in_oz: bool
    in_qct: bool
    persistent_poverty: bool
    status: str
    # Owner-level filter rollups (Slice 6 / #52, index schema v3). Defaulted so
    # a pre-v3 index still validates — the filters they back simply no-op then.
    counties: list[str] = Field(default_factory=list)
    structure_count: int = 0
    structure_types: list[str] = Field(default_factory=list)
    active_tower_count: int = 0
    tallest_tower_height_m: float | None = None
    # The antenna that sparked pursuit (#109, ADR-067/D2) — '' until pursued.
    # Per-tenant (derived from the flag activity row), attached at read time.
    trigger_asr: str = ""


class ContactAttemptOut(BaseModel):
    id: int
    occurred_on: str
    channel: str
    outcome: str
    note: str
    # outbound touch | inbound reply (#106, ADR-066). Defaulted so a row from
    # before the column existed still serializes.
    direction: str = "outbound"


class ContactAttemptIn(BaseModel):
    """A manually-logged activity event (date · channel · outcome).

    ``direction='inbound'`` logs a *reply* (the "Log reply" action, #106);
    the default ``'outbound'`` is a touch we made."""

    channel: str
    outcome: str = ""
    note: str = ""
    occurred_on: str | None = None  # ISO date; defaults to today server-side
    direction: str = "outbound"


# ── full Lead page detail (Slice 3 / #49) ───────────────────────────────────
class CarrierOut(BaseModel):
    """A ULS spectrum licensee identified on a tower (Slice A / #28). The
    confidence tag (verified/likely/possible) describes how the ULS license
    was tied to the tower in #24 — drives the badge the UI renders."""

    carrier_name: str = ""
    callsign: str = ""
    license_expiry: str = ""
    confidence_tag: str = ""


class Structure(BaseModel):
    """A tower or solar facility hosted on a holding. Tower fields
    (asr/height/lat/lon) are absent on solar entries and vice-versa."""

    type: str
    asr: str | None = None
    id: str | None = None
    height_m: float | None = None
    lat: float | None = None
    lon: float | None = None
    active: bool | None = None
    structure_kind: str | None = None
    owner: str | None = None
    # ULS licensee(s) on a tower (Slice A / #28). Declared here so FastAPI's
    # response_model passes them through (an undeclared field is dropped).
    # Defaulted so a pre-v4 owners index (no carriers) still validates.
    carriers: list[CarrierOut] = Field(default_factory=list)
    # Per-tower interestingness score (UI overhaul P1 / #105, ADR-067) — the
    # tower's underlying parcel's score, projected onto it. Declared so
    # response_model keeps it; None on a pre-v5 index (safe default).
    score: float | None = None


class Holding(BaseModel):
    """One parcel in a Lead's cross-state footprint."""

    parcel_id: str
    state: str
    county_fips: str = ""
    land_use: str = ""
    assessed_value: float = 0.0
    acreage: float | None = None
    tower_count: int = 0
    solar_count: int = 0
    # [minlng, minlat, maxlng, maxlat] and [lng, lat], EPSG:4326 — the
    # mini-map footprint. Either may be null when geometry is unavailable.
    bbox: list[float] | None = None
    point: list[float] | None = None
    structures: list[Structure] = Field(default_factory=list)


class MailingAddress(BaseModel):
    addr: str = ""
    city: str = ""
    state: str = ""
    zip: str = ""


class MergedMember(BaseModel):
    """A raw owner-cluster folded into this Lead by a manual merge (Slice 7 /
    #53). The Lead page lists these so the user can split one back out."""

    display_cluster_id: str
    owner_name: str


class LeadDetail(BaseModel):
    owner: OwnerSummary
    status: str
    notes: str
    updated_at: str | None
    attempts: list[ContactAttemptOut]
    # Editable contact record (distinct from the read-only mailing address).
    contact_name: str = ""
    contact_phone: str = ""
    contact_email: str = ""
    best_channel: str = ""
    # Read-only source detail for the "why this lead" + holdings halves.
    mailing_address: MailingAddress | None = None
    tallest_tower_height_m: float | None = None
    holdings: list[Holding] = Field(default_factory=list)
    # Owner-clusters merged into this Lead (Slice 7 / #53); empty when none.
    merged_members: list[MergedMember] = Field(default_factory=list)


class LeadUpdate(BaseModel):
    """Partial update — omit a field to leave it unchanged."""

    status: str | None = Field(default=None)
    notes: str | None = Field(default=None)
    contact_name: str | None = Field(default=None)
    contact_phone: str | None = Field(default=None)
    contact_email: str | None = Field(default=None)
    best_channel: str | None = Field(default=None)


class PursueBody(BaseModel):
    """Pursue an owner from Explore (#109). ``trigger_asr`` is the antenna that
    sparked it — recorded as the Lead's trigger."""

    trigger_asr: str = ""


class OverrideBody(BaseModel):
    """The other owner-cluster in a manual merge/split (Slice 7 / #53). The
    Lead being acted on is the path ``display_cluster_id`` (the survivor on
    merge); ``source_cluster_id`` is the cluster folded in / split back out."""

    source_cluster_id: str


class CandidatesResponse(BaseModel):
    count: int
    candidates: list[OwnerSummary]


class MyLeadsResponse(BaseModel):
    """The My-Leads worklist (Slice 5 / #51) — owners advanced off New, each
    carrying its status so the client buckets it into a kanban lane."""

    count: int
    leads: list[OwnerSummary]


class CountsResponse(BaseModel):
    """Live nav counts for the two list surfaces."""

    candidates: int
    my_leads: int


# ── per-antenna manual state (UI overhaul round 2) ───────────────────────────
class AntennaState(BaseModel):
    """The team's editable layer over one antenna (by ASR). All fields default
    so an antenna with no override row serializes as the empty/unedited state."""

    asr: str
    archived: bool = False
    address: str = ""
    owner_name: str = ""
    owner_phone: str = ""
    owner_email: str = ""
    notes: str = ""


class AntennaUpdate(BaseModel):
    """Partial update — omit a field to leave it unchanged."""

    archived: bool | None = None
    address: str | None = None
    owner_name: str | None = None
    owner_phone: str | None = None
    owner_email: str | None = None
    notes: str | None = None


class ArchivedAsrsResponse(BaseModel):
    """The ASRs the tenant has archived — the map + list drop these by default."""

    asrs: list[str]


# ── auth ─────────────────────────────────────────────────────────────────────
# Username/password login (Slice 1 / #76).
class LoginBody(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class MeResponse(BaseModel):
    tenant_id: int
    email: str
    # The signed-in user's team name (#86) — '' when the tenant has no Tenant
    # row (e.g. a session minted before teams existed).
    team: str = ""
    # The friendly name the user set in Settings (PRD #121); '' falls back to
    # the email at every render site (History/Stats/task assignment).
    display_name: str = ""


class MeUpdate(BaseModel):
    """Self-service identity edit (PRD #121). Only the display name is editable;
    email/team are administered via the credentials file."""

    display_name: str | None = Field(default=None)


class PasswordChange(BaseModel):
    """Self-service password change (PRD #121)."""

    current_password: str
    new_password: str


class UserSettingsResponse(BaseModel):
    """The resolved per-user preferences (PRD #121), defaults filled in. The
    ``home_view`` / ``filter_default`` fields are opaque JSON strings the client
    owns — the backend persists + serves them without inspecting."""

    theme: str
    colorblind: bool
    basemap: str
    view_mode: str
    home_view: str
    filter_default: str
    filter_default_apply: bool


class UserSettingsUpdate(BaseModel):
    """Upsert one or more per-user preference keys (PRD #121). Omit a field to
    leave it unchanged (the route reads ``model_fields_set``)."""

    theme: str | None = Field(default=None)
    colorblind: bool | None = Field(default=None)
    basemap: str | None = Field(default=None)
    view_mode: str | None = Field(default=None)
    home_view: str | None = Field(default=None)
    filter_default: str | None = Field(default=None)
    filter_default_apply: bool | None = Field(default=None)


# ── tasks (UI overhaul P2 / #107, fleshed out #110) ──────────────────────────
class TaskCreate(BaseModel):
    """Create a task. Links (owner/tower), assignee, due, priority, labels all
    optional (#110)."""

    title: str
    description: str = ""
    priority: str = "none"
    due_date: str | None = None  # ISO date
    assignee_user_id: int | None = None
    lead_cluster_id: str | None = None
    tower_asr: str | None = None
    labels: list[str] = Field(default_factory=list)


class TaskUpdate(BaseModel):
    """Partial update — omit a field to leave it unchanged. A nullable field
    sent as ``null`` clears it (the route reads ``model_fields_set``)."""

    title: str | None = Field(default=None)
    description: str | None = Field(default=None)
    status: str | None = Field(default=None)
    priority: str | None = Field(default=None)
    due_date: str | None = Field(default=None)
    assignee_user_id: int | None = Field(default=None)
    lead_cluster_id: str | None = Field(default=None)
    tower_asr: str | None = Field(default=None)
    labels: list[str] | None = Field(default=None)


class TaskOut(BaseModel):
    id: int
    title: str
    description: str
    status: str
    priority: str = "none"
    due_date: str | None = None
    assignee_user_id: int | None = None
    lead_cluster_id: str | None = None
    tower_asr: str | None = None
    labels: list[str] = Field(default_factory=list)
    source: str = "manual"
    created_by_user_id: int | None = None
    created_at: str
    updated_at: str
    completed_at: str | None = None


class TasksResponse(BaseModel):
    count: int
    tasks: list[TaskOut]


class UserOut(BaseModel):
    """A tenant teammate for the assignment UI (#110). ``name`` is the display
    name, falling back to the email."""

    id: int
    email: str
    display_name: str = ""
    name: str = ""


class UsersResponse(BaseModel):
    count: int
    users: list[UserOut]


# ── Dashboard attention feed (UI overhaul P2 / #111) ─────────────────────────
class AttentionItemOut(BaseModel):
    kind: str  # 'reply' | 'overdue_task'
    title: str
    when: str
    cluster_id: str = ""
    owner_name: str = ""
    task_id: int | None = None


class AttentionResponse(BaseModel):
    count: int
    items: list[AttentionItemOut]


class DismissBody(BaseModel):
    cluster_id: str


# ── Dashboard activity views: History + Calendar (UI overhaul P3 / #112) ─────
class ActivityEventOut(BaseModel):
    id: int  # ContactAttempt PK — stable key for keyed rendering
    date: str
    kind: str  # touch | reply | status | flag
    channel: str
    cluster_id: str
    owner_name: str = ""
    logged_by_user_id: int | None = None
    member_name: str = ""
    summary: str = ""


class ActivityResponse(BaseModel):
    count: int
    events: list[ActivityEventOut]
    last_contact_on: str | None = None
    last_reply_on: str | None = None


# ── Settings: automation (UI overhaul P5 / #116) ─────────────────────────────
class SettingsResponse(BaseModel):
    auto_followup_enabled: bool
    auto_followup_window_days: int


class SettingsUpdate(BaseModel):
    auto_followup_enabled: bool | None = None
    auto_followup_window_days: int | None = None


# ── Scoring presets (UI overhaul P4 / #115) ──────────────────────────────────
class ScoringPresetIn(BaseModel):
    name: str
    config: dict  # opaque to the backend (useDefault + weights)
    is_default: bool = False


class ScoringPresetOut(BaseModel):
    id: int
    name: str
    config: dict
    is_default: bool


class ScoringPresetsResponse(BaseModel):
    count: int
    presets: list[ScoringPresetOut]


# ── Dashboard Stats (UI overhaul P3 / #113) ──────────────────────────────────
class StatsResponse(BaseModel):
    funnel: dict[str, int]
    conversion: dict[str, float]
    reply_rate: float
    win_rate: float
    volume_by_channel: dict[str, int]
    activity_total: int
    active_days: int
    by_state: dict[str, dict[str, int]] = Field(default_factory=dict)
    by_member: dict[str, int] = Field(default_factory=dict)


# ── "Ask Claude" catalog helper (PRD #187 / #188) ────────────────────────────
class AskRequest(BaseModel):
    """The body of POST /api/audit/ask. Slice 1 is question-only (#188); the
    selection/page/signal grounding from the parent PRD layers on here later.

    ``min_length`` rejects an empty question; ``max_length`` bounds a single
    request so the typed input can't be used to push a huge prompt."""

    question: str = Field(min_length=1, max_length=4000)
