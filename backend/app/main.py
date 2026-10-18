"""FastAPI app — the thin Lead write-layer.

Surface:
  POST /api/auth/login           username/password → session JWT (httpOnly cookie + body)
  POST /api/auth/logout          clear the session cookie (PRD #130)
  POST /api/auth/demo            sign in as the read-only demo credential (DEMO_MODE, ADR-077)
  GET  /api/auth/config          public sign-in page config (is the demo login on?)
  GET  /api/auth/check           forward-auth seam for the edge /data gate (PRD #130)
  GET  /api/auth/me              the authenticated tenant + email
  GET  /api/health               liveness (public)
  GET  /api/candidates           owners at New, ranked by interestingness
  GET  /api/my-leads             owners advanced off New (the kanban worklist)
  GET  /api/counts               live nav counts (candidates + my-leads)
  GET  /api/leads/{cluster_id}   owner rollup + lead state + attempts
  PUT  /api/leads/{cluster_id}   set status and/or notes (validates ladder)
  POST /api/leads/{cluster_id}/merge   merge another owner-cluster into this Lead
  POST /api/leads/{cluster_id}/split   split a merged-in cluster back out
  GET/POST /api/tasks            list / create tasks (tenant-scoped)
  GET/PUT/DELETE /api/tasks/{id} read / update (title·desc·status) / delete a task
  GET/PUT /api/me/settings       per-user preferences (PRD #121; defaults filled in)
  PUT  /api/me                   update the signed-in user's display_name (PRD #121)
  POST /api/me/password          self-service password change (PRD #121, ADR-068)

Every data route resolves a tenant via ``current_tenant_id`` (now derived
from the bearer JWT — Slice 2 / #48) and goes through ``LeadStore`` /
``OwnersIndexService``, so every read and write is tenant-scoped and
unauthenticated requests are rejected with 401.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import date
from typing import TypeVar
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from .activity_service import ActivityService
from .antenna_store import AntennaStore
from .attention_service import DISMISS_CHANNEL, AttentionService
from .auth import (
    SESSION_COOKIE,
    Principal,
    create_access_token,
    current_principal,
    current_tenant_id,
    decode_access_token,
    session_token,
)
from .auth_service import InvalidCredentials, NotAuthorized, is_authorized, resolve_principal
from .auth_service import login as login_user
from .auto_followup_rule import AutoFollowUpRule
from .config import settings
from .credentials import normalize_username
from .credentials_store import CredentialsError, ensure_fail_closed_boot
from .credentials_store import get as get_credential
from .db import get_db, init_db
from .lead_status import InvalidTransition
from .lead_store import LeadStore
from .login_throttle import LoginThrottle
from .owner_merge_service import MergeError, OwnerMergeService
from .owners_index_service import OwnersIndexService
from .schemas import (
    ActivityEventOut,
    ActivityResponse,
    AntennaState,
    AntennaUpdate,
    ArchivedAsrsResponse,
    AttentionItemOut,
    AttentionResponse,
    AuthConfig,
    CandidatesResponse,
    ContactAttemptIn,
    CountsResponse,
    DismissBody,
    LeadDetail,
    LeadUpdate,
    LoginBody,
    MeResponse,
    MeUpdate,
    MyLeadsResponse,
    OverrideBody,
    OwnerSummary,
    PasswordChange,
    PursueBody,
    ScoringPresetIn,
    ScoringPresetOut,
    ScoringPresetsResponse,
    SettingsResponse,
    SettingsUpdate,
    StatsResponse,
    TaskCreate,
    TaskOut,
    TasksResponse,
    TaskUpdate,
    TokenResponse,
    UserOut,
    UserSettingsResponse,
    UserSettingsUpdate,
    UsersResponse,
    sent_fields,
)
from .scoring_preset_store import ScoringPresetStore
from .settings_store import (
    AUTO_FOLLOWUP_ENABLED,
    AUTO_FOLLOWUP_WINDOW_DAYS,
    KNOWN_KEYS,
    SettingsStore,
    UserSettingsStore,
)
from .stats_service import ActivityRow, LeadRow, StatsService
from .task_store import InvalidTaskPriority, InvalidTaskStatus, TaskStore
from .tenant_scoped_store import TenantScopedStore
from .tenant_service import TenantService
from .user_store import UserStore
from .users import ChangePasswordOutcome
from .users import change_password as users_change_password


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    init_db()
    # Fail-closed boot (ADR-069, preserving the ADR-062/063 posture): outside
    # dev mode the app refuses to serve without a real signing secret and at
    # least one credential row; dev mode seeds dev/dev through the same store
    # writer the CLI uses.
    ensure_fail_closed_boot()
    yield


app = FastAPI(title="Ground-Lease Lead Triage", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def csrf_origin_check(request: Request, call_next):
    """Cross-site request forgery guard (PRD #130): with the session riding in
    a cookie, a mutating request must come from our own origin.

    SameSite=Lax already blocks cross-site cookie sends on non-GET; this is the
    backstop. Browsers always attach ``Origin`` to non-GET requests — when it's
    present (or ``Referer`` as fallback) it must match the request's own host
    or a configured dev origin (the Vite proxy rewrites Host, so dev shows up
    as a cors_origins entry). A request with neither header is a non-browser
    client (curl, tests) — no ambient cookie context, so it passes; no
    token-dance CSRF machinery for a same-origin internal tool.
    """
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        source = request.headers.get("origin") or request.headers.get("referer")
        if source and not _same_origin(source, request):
            return JSONResponse(status_code=403, content={"detail": "cross-origin request refused"})
    return await call_next(request)


def _same_origin(source: str, request: Request) -> bool:
    """True when ``source`` (an Origin or Referer URL) is one of ours: the
    request's own Host, or an allowed dev origin from ``cors_origins``."""
    if any(source == o or source.startswith(o + "/") for o in settings.cors_origins):
        return True
    return urlsplit(source).netloc == request.headers.get("host", "")


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


_StoreT = TypeVar("_StoreT", bound=TenantScopedStore)


def tenant_store(cls: type[_StoreT]) -> Callable[..., _StoreT]:
    """Dependency factory for tenant-scoped stores: the one definition of the
    (session, tenant_id) wiring instead of a copied provider per store."""

    def dep(
        tenant_id: int = Depends(current_tenant_id),
        db: Session = Depends(get_db),
    ) -> _StoreT:
        return cls(db, tenant_id)

    return dep


# One provider per store, all built by the same factory. FastAPI caches the
# get_db dependency per request, so every store in a request shares one
# session/transaction (a write + its read are one transaction).
get_store = tenant_store(LeadStore)
get_merges = tenant_store(OwnerMergeService)
get_tasks = tenant_store(TaskStore)
get_antennas = tenant_store(AntennaStore)
get_presets = tenant_store(ScoringPresetStore)
get_settings = tenant_store(SettingsStore)
get_users = tenant_store(UserStore)


def get_user_settings(
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
) -> UserSettingsStore:
    """Per-user settings scoped to the resolved principal (PRD #121) — by both
    ``tenant_id`` *and* ``user_id``, so no teammate (or other tenant) can see
    another's preferences."""
    return UserSettingsStore(db, principal.tenant_id, principal.user_id)


def _auto_followup(store: LeadStore, db: Session, merges: OwnerMergeService) -> AutoFollowUpRule:
    """Build the auto-follow-up rule for a request (shares the session)."""
    return AutoFollowUpRule(
        store,
        TaskStore(db, store.tenant_id),
        SettingsStore(db, store.tenant_id),
        owner_name_of=lambda cid: (owners_index.get_owner(cid, merges) or {}).get("owner_name", ""),
    )


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "owners_indexed": owners_index.count}


@app.post("/api/auth/login", response_model=TokenResponse)
def login(
    body: LoginBody,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    throttle: LoginThrottle = Depends(get_login_throttle),
) -> TokenResponse:
    """Username/password sign-in: a session JWT on success, a specific 401 otherwise.

    The JWT is set in an httpOnly/Secure/SameSite=Lax cookie (PRD #130 — the
    SPA's transport; page scripts can never read it) and still returned in the
    body for non-browser clients (tests, curl). Same identity-only token (#88)
    either way: tenant/team are re-resolved from the credentials file on every
    request.

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
    return _start_session(response, principal.email)


def _start_session(response: Response, username: str) -> TokenResponse:
    """Mint the identity-only JWT for ``username`` and set it in the session
    cookie. The one place both sign-in routes issue a session."""
    token = create_access_token(username)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_ttl_days * 86400,
        httponly=True,
        # Dev runs over plain-HTTP localhost where some browsers drop Secure
        # cookies; production (dev_mode off) always sets it.
        secure=not settings.dev_mode,
        samesite="lax",
        path="/",
    )
    return TokenResponse(
        access_token=token,
        expires_in=settings.session_ttl_days * 86400,
    )


@app.get("/api/auth/config", response_model=AuthConfig)
def auth_config() -> AuthConfig:
    """Public: what the sign-in page should offer (ADR-077)."""
    return AuthConfig(demo_mode=settings.demo_mode)


@app.post("/api/auth/demo", response_model=TokenResponse)
def demo_login(response: Response, db: Session = Depends(get_db)) -> TokenResponse:
    """Sign in as the configured read-only demo credential, no password
    (ADR-077). 404 unless DEMO_MODE is on. The credential is re-checked here
    as well as at boot: if it was removed or made writable since, the route
    refuses rather than hand out a writable session. Nothing to brute-force,
    so no login throttle; the CSRF origin check still applies (POST)."""
    if not settings.demo_mode:
        raise HTTPException(status_code=404, detail="Not Found")
    entry = get_credential(db, settings.demo_username)
    if entry is None or not entry.read_only:
        raise HTTPException(status_code=404, detail="Not Found")
    try:
        principal = resolve_principal(db, entry.username)
    except NotAuthorized as exc:
        raise HTTPException(status_code=404, detail="Not Found") from exc
    return _start_session(response, principal.email)


@app.post("/api/auth/logout", status_code=204)
def logout(response: Response) -> None:
    """Sign out: clear the session cookie (PRD #130). After this the browser
    can no longer fetch the API *or* the gated /data files — actual sign-out,
    not just dropped client state. No auth required: clearing an absent or
    invalid cookie is harmless and must never fail."""
    response.delete_cookie(SESSION_COOKIE, path="/")


@app.get("/api/auth/check", status_code=204)
def auth_check(token: str = Depends(session_token), db: Session = Depends(get_db)) -> None:
    """Forward-auth seam for the edge (PRD #130): Caddy asks this before
    serving any byte under ``/data/processed/*``. Validates the session
    (cookie first, bearer fallback) and re-checks the username against the
    credential table — per-request authority extends to the data plane, so a
    removed user loses file access on their next fetch. 204 on success, 401
    otherwise. One indexed SELECT — no tenant/user resolution, since the
    edge only needs yes/no."""
    username = decode_access_token(token)
    if not is_authorized(db, username):
        raise HTTPException(
            status_code=401,
            detail="not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _me_response(principal: Principal, db: Session, users: UserStore) -> MeResponse:
    user = users.get(principal.user_id)
    return MeResponse(
        tenant_id=principal.tenant_id,
        email=principal.email,
        # The team name lives on the Tenant row (#86), not in the JWT — #88
        # makes the JWT identity-only, so nothing tenant-shaped is added to it.
        team=TenantService(db).get_name(principal.tenant_id),
        display_name=user.display_name if user is not None else "",
        read_only=principal.read_only,
    )


@app.get("/api/auth/me", response_model=MeResponse)
def me(
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
    users: UserStore = Depends(get_users),
) -> MeResponse:
    return _me_response(principal, db, users)


@app.put("/api/me", response_model=MeResponse)
def update_me(
    body: MeUpdate,
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
    users: UserStore = Depends(get_users),
) -> MeResponse:
    """Edit the signed-in user's display name (PRD #121). A blank name is
    allowed — it falls back to the email at every render site."""
    if "display_name" in body.model_fields_set and body.display_name is not None:
        users.set_display_name(principal.user_id, body.display_name)
    return _me_response(principal, db, users)


def _user_settings_out(s: UserSettingsStore) -> UserSettingsResponse:
    r = s.resolved()
    return UserSettingsResponse(
        theme=r["theme"],
        colorblind=r["colorblind"] == "1",
        basemap=r["basemap"],
        view_mode=r["view_mode"],
        home_view=r["home_view"],
        filter_default=r["filter_default"],
        filter_default_apply=r["filter_default_apply"] == "1",
    )


@app.get("/api/me/settings", response_model=UserSettingsResponse)
def get_my_settings(s: UserSettingsStore = Depends(get_user_settings)) -> UserSettingsResponse:
    return _user_settings_out(s)


@app.put("/api/me/settings", response_model=UserSettingsResponse)
def update_my_settings(
    body: UserSettingsUpdate, s: UserSettingsStore = Depends(get_user_settings)
) -> UserSettingsResponse:
    """Upsert one or more preference keys (PRD #121). ``home_view`` /
    ``filter_default`` are opaque client-owned blobs persisted verbatim — the
    backend never inspects them (same posture as ``ScoringPreset.config``)."""
    for key, value in sent_fields(body, KNOWN_KEYS).items():
        # bool prefs are stored as "0"/"1"; everything else is a string.
        s.set(key, ("1" if value else "0") if isinstance(value, bool) else str(value))
    return _user_settings_out(s)


@app.post("/api/me/password", status_code=204)
def change_my_password(
    body: PasswordChange,
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
) -> None:
    """Self-service password change (PRD #121). Routes through the *one*
    sanctioned runtime writer (``users.change_password`` → the store's
    password writer); wrong current password → 401 (nothing written),
    success is live on the next login attempt."""
    try:
        outcome = users_change_password(
            db,
            principal.email,
            body.current_password,
            body.new_password,
        )
    except CredentialsError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if outcome is ChangePasswordOutcome.WRONG_CURRENT:
        raise HTTPException(status_code=401, detail="Current password is incorrect")


@app.get("/api/candidates", response_model=CandidatesResponse)
def candidates(
    store: LeadStore = Depends(get_store),
    merges: OwnerMergeService = Depends(get_merges),
    limit: int = Query(default=200, ge=1, le=2000),
) -> CandidatesResponse:
    rows = owners_index.list_candidates(store, limit=limit, merges=merges)
    # model_construct skips the in-route validation pass on our own trusted
    # index rows (PERF-024); response_model still validates once on the way out.
    return CandidatesResponse(
        count=len(rows),
        candidates=[OwnerSummary.model_construct(**r) for r in rows],
    )


@app.get("/api/my-leads", response_model=MyLeadsResponse)
def my_leads(
    store: LeadStore = Depends(get_store),
    merges: OwnerMergeService = Depends(get_merges),
    limit: int = Query(default=2000, ge=1, le=20000),
) -> MyLeadsResponse:
    rows = owners_index.list_my_leads(store, limit=limit, merges=merges)
    return MyLeadsResponse(count=len(rows), leads=[OwnerSummary.model_construct(**r) for r in rows])


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
    return LeadDetail.model_validate(view)


@app.put("/api/leads/{display_cluster_id}", response_model=LeadDetail)
def update_lead(
    display_cluster_id: str,
    body: LeadUpdate,
    store: LeadStore = Depends(get_store),
    merges: OwnerMergeService = Depends(get_merges),
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
) -> LeadDetail:
    if owners_index.get_owner(display_cluster_id, merges) is None:
        raise HTTPException(status_code=404, detail="owner not found in index")
    # Honor coalesce on writes too: a merged-away source id persists onto the
    # surviving target row, so what the user sees is what they edit.
    target = merges.resolve(display_cluster_id)
    contact = sent_fields(body, LeadStore.CONTACT_FIELDS)
    try:
        store.upsert(
            target,
            status=body.status,
            notes=body.notes,
            contact=contact or None,
            logged_by_user_id=principal.user_id,
        )
    except InvalidTransition as exc:
        # 409 Conflict — the request is well-formed but illegal for this Lead's state.
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    # Auto follow-up (#116): moving to Contacted eagerly schedules a chase.
    if body.status == "contacted":
        _auto_followup(store, db, merges).maybe_schedule(
            target, anchor=date.today(), status="contacted"
        )
    view = owners_index.lead_view(store, display_cluster_id, merges=merges)
    assert view is not None  # owner existence checked above
    return LeadDetail.model_validate(view)


@app.post("/api/leads/{display_cluster_id}/attempts", response_model=LeadDetail)
def log_attempt(
    display_cluster_id: str,
    body: ContactAttemptIn,
    store: LeadStore = Depends(get_store),
    merges: OwnerMergeService = Depends(get_merges),
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
) -> LeadDetail:
    """Append a manual activity event (date · channel · outcome) to the log.

    ``direction='inbound'`` records a *reply* (the "Log reply" flow, #106);
    the default ``'outbound'`` is a touch we made. Status-transition rows are
    auto-logged on ``PUT`` instead; this is the user explicitly recording
    an outreach event or a reply."""
    if owners_index.get_owner(display_cluster_id, merges) is None:
        raise HTTPException(status_code=404, detail="owner not found in index")
    if not body.channel.strip():
        raise HTTPException(status_code=422, detail="channel is required")
    if body.direction not in ("outbound", "inbound"):
        raise HTTPException(status_code=422, detail="direction must be outbound or inbound")
    occurred_on = _parse_iso_date(body.occurred_on)
    target = merges.resolve(display_cluster_id)
    store.append_attempt(
        target,
        channel=body.channel,
        outcome=body.outcome,
        note=body.note,
        occurred_on=occurred_on,
        direction=body.direction,
        logged_by_user_id=principal.user_id,
    )
    # Auto follow-up (#116): an inbound reply cancels the open chase; an
    # outbound touch (not a status/flag row) schedules one if eligible.
    rule = _auto_followup(store, db, merges)
    if body.direction == "inbound":
        rule.cancel_on_reply(target)
    elif body.channel not in ("status", "flag", "dismiss"):
        lead = store.get_lead(target)
        rule.maybe_schedule(
            target,
            anchor=occurred_on or date.today(),
            status=lead.status if lead else "new",
        )
    view = owners_index.lead_view(store, display_cluster_id, merges=merges)
    assert view is not None
    return LeadDetail.model_validate(view)


@app.post("/api/leads/{display_cluster_id}/pursue", response_model=LeadDetail)
def pursue_owner(
    display_cluster_id: str,
    body: PursueBody,
    store: LeadStore = Depends(get_store),
    merges: OwnerMergeService = Depends(get_merges),
    principal: Principal = Depends(current_principal),
) -> LeadDetail:
    """Pursue an owner from Explore (#109, ADR-067): advance New → Researching
    and record the triggering antenna (a ``channel='flag'`` activity row). The
    whole owner becomes a Lead (one human, one call); the trigger preserves the
    discovery context. Idempotent — pursuing a worked owner just adds a trigger."""
    if owners_index.get_owner(display_cluster_id, merges) is None:
        raise HTTPException(status_code=404, detail="owner not found in index")
    store.pursue(
        merges.resolve(display_cluster_id),
        trigger_asr=body.trigger_asr,
        logged_by_user_id=principal.user_id,
    )
    view = owners_index.lead_view(store, display_cluster_id, merges=merges)
    assert view is not None
    return LeadDetail.model_validate(view)


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
    return LeadDetail.model_validate(view)


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
    return LeadDetail.model_validate(view)


# ── per-antenna manual state (UI overhaul round 2) ────────────────────────────
def _antenna_state(asr: str, row) -> AntennaState:
    """The override row validated straight into the schema, or the
    empty/unedited state when no row exists (asr comes from the path)."""
    return AntennaState.model_validate(row) if row is not None else AntennaState(asr=asr)


@app.get("/api/antennas/archived", response_model=ArchivedAsrsResponse)
def list_archived_antennas(
    antennas: AntennaStore = Depends(get_antennas),
) -> ArchivedAsrsResponse:
    """The ASRs this tenant has archived — the Explore map + list drop these
    unless the user toggles "show archived". Declared before the ``/{asr}``
    route so the literal path wins the match."""
    return ArchivedAsrsResponse(asrs=sorted(antennas.archived_asrs()))


@app.get("/api/antennas/{asr}", response_model=AntennaState)
def get_antenna(asr: str, antennas: AntennaStore = Depends(get_antennas)) -> AntennaState:
    """The team's manual layer over one antenna (address / archived / manual
    owner details). Empty when never edited."""
    return _antenna_state(asr, antennas.get(asr))


@app.put("/api/antennas/{asr}", response_model=AntennaState)
def update_antenna(
    asr: str,
    body: AntennaUpdate,
    antennas: AntennaStore = Depends(get_antennas),
) -> AntennaState:
    """Set the archived flag and/or any subset of the editable fields for an
    antenna. Only fields actually sent are touched (``model_fields_set``), so
    archiving doesn't clear an address and vice-versa."""
    fields = sent_fields(body, AntennaStore.EDITABLE)
    archived = sent_fields(body, ("archived",)).get("archived")
    row = antennas.upsert(asr, archived=archived, fields=fields or None)
    return _antenna_state(asr, row)


# ── tasks (UI overhaul P2 / #107, filtering #110) ─────────────────────────────
@app.get("/api/tasks", response_model=TasksResponse)
def list_tasks(
    tasks: TaskStore = Depends(get_tasks),
    status: str | None = Query(default=None),
    priority: str | None = Query(default=None),
    assignee: int | None = Query(default=None),
    unassigned: bool = Query(default=False),
    lead: str | None = Query(default=None),
    tower: str | None = Query(default=None),
    source: str | None = Query(default=None),
    label: str | None = Query(default=None),
    due_before: str | None = Query(default=None),
    q: str | None = Query(default=None),
) -> TasksResponse:
    """List the tenant's tasks, narrowed by any subset of fields (#110)."""
    rows = tasks.list_filtered(
        status=status,
        priority=priority,
        assignee_user_id=assignee,
        unassigned=unassigned,
        lead_cluster_id=lead,
        tower_asr=tower,
        source=source,
        label=label,
        due_before=_parse_iso_date(due_before),
        q=q,
    )
    return TasksResponse(count=len(rows), tasks=[TaskOut.model_validate(t) for t in rows])


@app.post("/api/tasks", response_model=TaskOut)
def create_task(
    body: TaskCreate,
    tasks: TaskStore = Depends(get_tasks),
    principal: Principal = Depends(current_principal),
) -> TaskOut:
    if not body.title.strip():
        raise HTTPException(status_code=422, detail="title is required")
    try:
        task = tasks.create(
            title=body.title,
            description=body.description,
            priority=body.priority,
            due_date=_parse_iso_date(body.due_date),
            assignee_user_id=body.assignee_user_id,
            lead_cluster_id=body.lead_cluster_id,
            tower_asr=body.tower_asr,
            labels=body.labels,
            created_by_user_id=principal.user_id,
        )
    except InvalidTaskPriority as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return TaskOut.model_validate(task)


@app.get("/api/tasks/{task_id}", response_model=TaskOut)
def get_task(task_id: int, tasks: TaskStore = Depends(get_tasks)) -> TaskOut:
    task = tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return TaskOut.model_validate(task)


@app.put("/api/tasks/{task_id}", response_model=TaskOut)
def update_task(
    task_id: int,
    body: TaskUpdate,
    tasks: TaskStore = Depends(get_tasks),
) -> TaskOut:
    if body.title is not None and not body.title.strip():
        raise HTTPException(status_code=422, detail="title cannot be blank")
    # Only fields the client actually sent; for the sentinel-clearable fields
    # a sent null passes through so it clears the link/due/assignee (#110).
    kwargs = sent_fields(body, ("title", "description", "status", "priority", "labels"))
    kwargs |= sent_fields(
        body, ("due_date", "assignee_user_id", "lead_cluster_id", "tower_asr"), keep_none=True
    )
    if "due_date" in kwargs:
        kwargs["due_date"] = _parse_iso_date(kwargs["due_date"])
    try:
        task = tasks.update(task_id, **kwargs)
    except InvalidTaskStatus as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except InvalidTaskPriority as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return TaskOut.model_validate(task)


@app.delete("/api/tasks/{task_id}", status_code=204)
def delete_task(task_id: int, tasks: TaskStore = Depends(get_tasks)) -> None:
    if not tasks.delete(task_id):
        raise HTTPException(status_code=404, detail="task not found")


# ── Dashboard: attention feed (#111) ──────────────────────────────────────────
@app.get("/api/attention", response_model=AttentionResponse)
def attention(
    store: LeadStore = Depends(get_store),
    tasks: TaskStore = Depends(get_tasks),
    merges: OwnerMergeService = Depends(get_merges),
    principal: Principal = Depends(current_principal),
) -> AttentionResponse:
    """Unhandled inbound replies + overdue tasks (mine or unassigned) — the
    Dashboard attention feed + nav badge (#111, D10)."""
    svc = AttentionService(
        store,
        tasks,
        user_id=principal.user_id,
        today=date.today(),
        owner_name_of=lambda cid: (owners_index.get_owner(cid, merges) or {}).get("owner_name", ""),
    )
    items = svc.items()
    return AttentionResponse(
        count=len(items),
        items=[AttentionItemOut.model_validate(i) for i in items],
    )


@app.post("/api/attention/dismiss")
def dismiss_attention(
    body: DismissBody,
    store: LeadStore = Depends(get_store),
    merges: OwnerMergeService = Depends(get_merges),
    principal: Principal = Depends(current_principal),
) -> dict:
    """Dismiss a Lead's unhandled reply by appending a newer activity row (the
    "newer activity clears it" rule subsumes dismissal — D10). Attributed to the
    dismissing user so it carries a teammate dimension in activity/stats."""
    store.append_attempt(
        merges.resolve(body.cluster_id),
        channel=DISMISS_CHANNEL,
        outcome="dismissed",
        logged_by_user_id=principal.user_id,
    )
    return {"ok": True}


# ── Settings: automation (#116) ───────────────────────────────────────────────
@app.get("/api/settings", response_model=SettingsResponse)
def get_tenant_settings(settings: SettingsStore = Depends(get_settings)) -> SettingsResponse:
    return SettingsResponse.model_validate(settings)


@app.put("/api/settings", response_model=SettingsResponse)
def update_tenant_settings(
    body: SettingsUpdate, settings: SettingsStore = Depends(get_settings)
) -> SettingsResponse:
    if body.auto_followup_enabled is not None:
        settings.set(AUTO_FOLLOWUP_ENABLED, "1" if body.auto_followup_enabled else "0")
    if body.auto_followup_window_days is not None:
        if body.auto_followup_window_days < 1:
            raise HTTPException(status_code=422, detail="window must be ≥ 1 day")
        settings.set(AUTO_FOLLOWUP_WINDOW_DAYS, str(body.auto_followup_window_days))
    return SettingsResponse.model_validate(settings)


# ── Scoring presets (#115) — tenant-shared named scoring configs ──────────────
@app.get("/api/scoring-presets", response_model=ScoringPresetsResponse)
def list_scoring_presets(
    presets: ScoringPresetStore = Depends(get_presets),
) -> ScoringPresetsResponse:
    rows = presets.list()
    return ScoringPresetsResponse(
        count=len(rows), presets=[ScoringPresetOut.model_validate(p) for p in rows]
    )


@app.post("/api/scoring-presets", response_model=ScoringPresetOut)
def create_scoring_preset(
    body: ScoringPresetIn, presets: ScoringPresetStore = Depends(get_presets)
) -> ScoringPresetOut:
    if not body.name.strip():
        raise HTTPException(status_code=422, detail="name is required")
    p = presets.create(
        name=body.name.strip(), config=json.dumps(body.config), is_default=body.is_default
    )
    return ScoringPresetOut.model_validate(p)


@app.post("/api/scoring-presets/{preset_id}/default", response_model=ScoringPresetOut)
def set_default_scoring_preset(
    preset_id: int, presets: ScoringPresetStore = Depends(get_presets)
) -> ScoringPresetOut:
    p = presets.set_default(preset_id)
    if p is None:
        raise HTTPException(status_code=404, detail="preset not found")
    return ScoringPresetOut.model_validate(p)


@app.delete("/api/scoring-presets/{preset_id}", status_code=204)
def delete_scoring_preset(
    preset_id: int, presets: ScoringPresetStore = Depends(get_presets)
) -> None:
    if not presets.delete(preset_id):
        raise HTTPException(status_code=404, detail="preset not found")


# ── Dashboard: Stats (#113) ───────────────────────────────────────────────────
@app.get("/api/stats", response_model=StatsResponse)
def stats(
    store: LeadStore = Depends(get_store),
    merges: OwnerMergeService = Depends(get_merges),
    users: UserStore = Depends(get_users),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    state: str | None = Query(default=None),
    member: int | None = Query(default=None),
) -> StatsResponse:
    """Outreach analytics derived from leads + activity (#113, D11): funnel,
    conversion, reply/win rate, volume by channel; date-range filter; member
    + state breakdowns. No new write data."""
    owners, _ = owners_index.effective(merges)
    status_by_id = store.status_map()
    # StatsService only reads ``states`` (membership + iteration), never mutates
    # it — so pass the index's own list rather than copying it 16k times per call
    # (PERF-017, the safe slice of the finding).
    leads = [
        LeadRow(
            cid=o["display_cluster_id"],
            states=o.get("states") or [],
            status=status_by_id.get(o["display_cluster_id"], "new"),
        )
        for o in owners
    ]
    attempts = [
        ActivityRow(
            occurred_on=a.occurred_on,
            channel=a.channel,
            direction=a.direction,
            cid=a.display_cluster_id,
            logged_by_user_id=a.logged_by_user_id,
        )
        for a in store.tenant_attempts()
    ]
    names = users.names_by_id()
    # Unknown / null author (e.g. legacy rows, or system-generated activity) →
    # "Unattributed" rather than the raw "user None"/"user 7".
    svc = StatsService(leads, attempts, member_name_of=lambda uid: names.get(uid, "Unattributed"))
    r = svc.compute(
        date_from=_parse_iso_date(date_from),
        date_to=_parse_iso_date(date_to),
        state=state,
        member=member,
    )
    return StatsResponse.model_validate(r)


# ── Dashboard: activity views — History + Calendar (#112) ─────────────────────
@app.get("/api/activity", response_model=ActivityResponse)
def activity(
    store: LeadStore = Depends(get_store),
    merges: OwnerMergeService = Depends(get_merges),
    users: UserStore = Depends(get_users),
    lead: str | None = Query(default=None),
    member: int | None = Query(default=None),
    channel: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
) -> ActivityResponse:
    """The shared activity read model (#112, D9): the tenant's time-ordered
    activity, narrowed by lead / member / channel / date range. History renders
    it chronologically; Calendar buckets it by date. Includes the recent-
    activity digest (last contact + last reply)."""
    names = users.names_by_id()
    # Resolve the effective index once per request (PERF-009) — the per-row
    # owner_name_of then does O(1) lookups instead of rebuilding the merged
    # index for every activity row.
    _, by_id = owners_index.effective(merges)
    svc = ActivityService(
        store,
        owner_name_of=lambda cid: (by_id.get(merges.resolve(cid)) or {}).get("owner_name", ""),
        member_name_of=lambda uid: names.get(uid, "") if uid is not None else "",
    )
    events = svc.events(
        lead=lead,
        member=member,
        channel=channel,
        date_from=_parse_iso_date(date_from),
        date_to=_parse_iso_date(date_to),
    )
    digest = svc.digest()
    return ActivityResponse(
        count=len(events),
        events=[ActivityEventOut.model_validate(e) for e in events],
        last_contact_on=digest["last_contact_on"],
        last_reply_on=digest["last_reply_on"],
    )


@app.get("/api/users", response_model=UsersResponse)
def list_users(users: UserStore = Depends(get_users)) -> UsersResponse:
    """The tenant's teammates for task assignment (#110)."""
    rows = users.list_by_email()
    return UsersResponse(count=len(rows), users=[UserOut.model_validate(u) for u in rows])


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="occurred_on must be ISO date") from exc
