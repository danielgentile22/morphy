"""FastAPI app — the thin Lead write-layer.

Surface:
  POST /api/auth/login           username/password → short-lived session JWT
  GET  /api/auth/me              the authenticated tenant + email
  GET  /api/health               liveness (public)
  GET  /api/candidates           owners at New, ranked by interestingness
  GET  /api/my-leads             owners advanced off New (the kanban worklist)
  GET  /api/counts               live nav counts (candidates + my-leads)
  GET  /api/leads/{cluster_id}   owner rollup + lead state + attempts
  PUT  /api/leads/{cluster_id}   set status and/or notes (validates ladder)
  POST /api/leads/{cluster_id}/merge   merge another owner-cluster into this Lead
  POST /api/leads/{cluster_id}/split   split a merged-in cluster back out

Every data route resolves a tenant via ``current_tenant_id`` (now derived
from the bearer JWT — Slice 2 / #48) and goes through ``LeadStore`` /
``OwnersIndexService``, so every read and write is tenant-scoped and
unauthenticated requests are rejected with 401.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from datetime import date

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .auth import Principal, create_access_token, current_principal, current_tenant_id
from .auth_service import InvalidCredentials
from .auth_service import login as login_user
from .config import settings
from .credentials import normalize_username
from .db import get_db, init_db
from .lead_status import InvalidTransition
from .lead_store import LeadStore
from .login_throttle import LoginThrottle
from .owner_merge_service import MergeError, OwnerMergeService
from .owners_index_service import OwnersIndexService
from .schemas import (
    CandidatesResponse,
    ContactAttemptIn,
    CountsResponse,
    LeadDetail,
    LeadUpdate,
    LoginBody,
    MeResponse,
    MyLeadsResponse,
    OverrideBody,
    OwnerSummary,
    TokenResponse,
)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    init_db()
    yield


app = FastAPI(title="Ground-Lease Lead Triage", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_methods=["*"],
    allow_headers=["*"],
)

# The owners index is static + shared; load once at import.
owners_index = OwnersIndexService(settings.owners_index_path)

# In-process login brute-force throttle (Slice 2 / #77). One shared instance —
# its sliding-window state is the whole point, so it must outlive a request.
# Tests override ``get_login_throttle`` with a clock-injected instance.
_login_throttle = LoginThrottle(
    max_failures=settings.login_throttle_max,
    window_seconds=settings.login_throttle_window_seconds,
)


def get_login_throttle() -> LoginThrottle:
    return _login_throttle


def get_store(
    tenant_id: int = Depends(current_tenant_id),
    db: Session = Depends(get_db),
) -> Iterator[LeadStore]:
    yield LeadStore(db, tenant_id)


def get_merges(
    tenant_id: int = Depends(current_tenant_id),
    db: Session = Depends(get_db),
) -> OwnerMergeService:
    # Shares the request-scoped session with get_store (FastAPI caches the
    # get_db dependency per request), so a write + its read are one transaction.
    return OwnerMergeService(db, tenant_id)


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "owners_indexed": owners_index.count}


@app.post("/api/auth/login", response_model=TokenResponse)
def login(
    body: LoginBody,
    request: Request,
    db: Session = Depends(get_db),
    throttle: LoginThrottle = Depends(get_login_throttle),
) -> TokenResponse:
    """Username/password sign-in: a session JWT on success, a specific 401 otherwise.

    A brute-force throttle (#77) keyed by ``(ip, username)`` short-circuits with
    429 once failures pass the limit within the window — even a correct password
    is refused while blocked. The block self-clears as the window rolls forward
    (no hard lockout), and a successful login resets the key.
    """
    ip = request.client.host if request.client else "unknown"
    key = (ip, normalize_username(body.username))
    if throttle.is_blocked(key):
        raise HTTPException(
            status_code=429,
            detail="Too many failed login attempts; try again later.",
            headers={"Retry-After": str(int(throttle.retry_after(key)) + 1)},
        )
    try:
        principal = login_user(db, username=body.username, password=body.password)
    except InvalidCredentials as exc:
        throttle.record_failure(key)
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    throttle.reset(key)  # a real sign-in clears the counter for this key
    return TokenResponse(
        access_token=create_access_token(principal),
        expires_in=settings.session_ttl_days * 86400,
    )


@app.get("/api/auth/me", response_model=MeResponse)
def me(principal: Principal = Depends(current_principal)) -> MeResponse:
    return MeResponse(tenant_id=principal.tenant_id, email=principal.email)


@app.get("/api/candidates", response_model=CandidatesResponse)
def candidates(
    store: LeadStore = Depends(get_store),
    merges: OwnerMergeService = Depends(get_merges),
    limit: int = Query(default=200, ge=1, le=2000),
) -> CandidatesResponse:
    rows = owners_index.list_candidates(store, limit=limit, merges=merges)
    return CandidatesResponse(
        count=len(rows),
        candidates=[OwnerSummary(**r) for r in rows],
    )


@app.get("/api/my-leads", response_model=MyLeadsResponse)
def my_leads(
    store: LeadStore = Depends(get_store),
    merges: OwnerMergeService = Depends(get_merges),
    limit: int = Query(default=2000, ge=1, le=20000),
) -> MyLeadsResponse:
    rows = owners_index.list_my_leads(store, limit=limit, merges=merges)
    return MyLeadsResponse(count=len(rows), leads=[OwnerSummary(**r) for r in rows])


@app.get("/api/counts", response_model=CountsResponse)
def counts(
    store: LeadStore = Depends(get_store),
    merges: OwnerMergeService = Depends(get_merges),
) -> CountsResponse:
    return CountsResponse(**owners_index.counts(store, merges=merges))


@app.get("/api/leads/{display_cluster_id}", response_model=LeadDetail)
def get_lead(
    display_cluster_id: str,
    store: LeadStore = Depends(get_store),
    merges: OwnerMergeService = Depends(get_merges),
) -> LeadDetail:
    view = owners_index.lead_view(store, display_cluster_id, merges=merges)
    if view is None:
        raise HTTPException(status_code=404, detail="owner not found in index")
    return _to_detail(view)


@app.put("/api/leads/{display_cluster_id}", response_model=LeadDetail)
def update_lead(
    display_cluster_id: str,
    body: LeadUpdate,
    store: LeadStore = Depends(get_store),
    merges: OwnerMergeService = Depends(get_merges),
) -> LeadDetail:
    if owners_index.get_owner(display_cluster_id, merges) is None:
        raise HTTPException(status_code=404, detail="owner not found in index")
    # Honor coalesce on writes too: a merged-away source id persists onto the
    # surviving target row, so what the user sees is what they edit.
    target = merges.resolve(display_cluster_id)
    contact = {
        f: getattr(body, f) for f in LeadStore.CONTACT_FIELDS if getattr(body, f) is not None
    }
    try:
        store.upsert(
            target,
            status=body.status,
            notes=body.notes,
            contact=contact or None,
        )
    except InvalidTransition as exc:
        # 409 Conflict — the request is well-formed but illegal for this Lead's state.
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    view = owners_index.lead_view(store, display_cluster_id, merges=merges)
    assert view is not None  # owner existence checked above
    return _to_detail(view)


@app.post("/api/leads/{display_cluster_id}/attempts", response_model=LeadDetail)
def log_attempt(
    display_cluster_id: str,
    body: ContactAttemptIn,
    store: LeadStore = Depends(get_store),
    merges: OwnerMergeService = Depends(get_merges),
) -> LeadDetail:
    """Append a manual contact attempt (date · channel · outcome) to the log.

    Status-transition rows are auto-logged on ``PUT`` instead; this is the
    co-founder explicitly recording an outreach event."""
    if owners_index.get_owner(display_cluster_id, merges) is None:
        raise HTTPException(status_code=404, detail="owner not found in index")
    if not body.channel.strip():
        raise HTTPException(status_code=422, detail="channel is required")
    occurred_on = _parse_iso_date(body.occurred_on)
    store.append_attempt(
        merges.resolve(display_cluster_id),
        channel=body.channel,
        outcome=body.outcome,
        note=body.note,
        occurred_on=occurred_on,
    )
    view = owners_index.lead_view(store, display_cluster_id, merges=merges)
    assert view is not None
    return _to_detail(view)


@app.post("/api/leads/{display_cluster_id}/merge", response_model=LeadDetail)
def merge_cluster(
    display_cluster_id: str,
    body: OverrideBody,
    store: LeadStore = Depends(get_store),
    merges: OwnerMergeService = Depends(get_merges),
) -> LeadDetail:
    """Merge ``source_cluster_id`` into this Lead (the path id is the survivor).

    Both clusters must exist in the owners index. Afterward the source resolves
    to this Lead everywhere (map, Candidates, kanban, Lead page). Overrides live
    in Postgres keyed on raw cluster ids, so they survive an index recompute."""
    target = merges.resolve(display_cluster_id)
    if owners_index.get_owner(target) is None:
        raise HTTPException(status_code=404, detail="owner not found in index")
    if owners_index.get_owner(body.source_cluster_id) is None:
        raise HTTPException(status_code=404, detail="source owner not found in index")
    try:
        merges.merge(source=body.source_cluster_id, target=target)
    except MergeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    view = owners_index.lead_view(store, target, merges=merges)
    assert view is not None
    return _to_detail(view)


@app.post("/api/leads/{display_cluster_id}/split", response_model=LeadDetail)
def split_cluster(
    display_cluster_id: str,
    body: OverrideBody,
    store: LeadStore = Depends(get_store),
    merges: OwnerMergeService = Depends(get_merges),
) -> LeadDetail:
    """Split ``source_cluster_id`` back out of this Lead — it returns to its own
    raw cluster as an independent Lead. Reverses a prior merge (no lead state
    was ever moved, so the source's own status/notes/attempts are intact)."""
    target = merges.resolve(display_cluster_id)
    if owners_index.get_owner(target) is None:
        raise HTTPException(status_code=404, detail="owner not found in index")
    if not merges.split(source=body.source_cluster_id):
        raise HTTPException(status_code=404, detail="no merge override to split")
    view = owners_index.lead_view(store, target, merges=merges)
    assert view is not None
    return _to_detail(view)


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="occurred_on must be ISO date") from exc


def _to_detail(view: dict) -> LeadDetail:
    owner = OwnerSummary(**{**view["owner"], "status": view["status"]})
    return LeadDetail(
        owner=owner,
        status=view["status"],
        notes=view["notes"],
        updated_at=view["updated_at"],
        attempts=view["attempts"],
        contact_name=view["contact_name"],
        contact_phone=view["contact_phone"],
        contact_email=view["contact_email"],
        best_channel=view["best_channel"],
        mailing_address=view["mailing_address"],
        tallest_tower_height_m=view["tallest_tower_height_m"],
        holdings=view["holdings"],
        merged_members=view.get("merged_members", []),
    )
