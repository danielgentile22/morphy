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


class ContactAttemptOut(BaseModel):
    id: int
    occurred_on: str
    channel: str
    outcome: str
    note: str


class ContactAttemptIn(BaseModel):
    """A manually-logged outreach attempt (date · channel · outcome)."""

    channel: str
    outcome: str = ""
    note: str = ""
    occurred_on: str | None = None  # ISO date; defaults to today server-side


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


# ── auth (Slice 2 / #48) ────────────────────────────────────────────────────
# Email is a plain ``str`` (lightly validated server-side) to avoid pulling
# in pydantic's optional ``email-validator`` dependency.
class RequestLinkBody(BaseModel):
    email: str


class RequestLinkResponse(BaseModel):
    ok: bool
    # Present only when AUTH_EXPOSE_TOKEN is on (dev) so the SPA can complete
    # the exchange without a real inbox. Never set in prod.
    dev_token: str | None = None


class ExchangeBody(BaseModel):
    token: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class MeResponse(BaseModel):
    tenant_id: int
    email: str
