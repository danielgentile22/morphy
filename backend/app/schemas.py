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


class ContactAttemptOut(BaseModel):
    id: int
    occurred_on: str
    channel: str
    outcome: str
    note: str


class LeadDetail(BaseModel):
    owner: OwnerSummary
    status: str
    notes: str
    updated_at: str | None
    attempts: list[ContactAttemptOut]


class LeadUpdate(BaseModel):
    """Partial update — omit a field to leave it unchanged."""

    status: str | None = Field(default=None)
    notes: str | None = Field(default=None)


class CandidatesResponse(BaseModel):
    count: int
    candidates: list[OwnerSummary]


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
