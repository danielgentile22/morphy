"""FastAPI app — the thin Lead write-layer (Slice 1 tracer).

Surface:
  GET  /api/health
  GET  /api/candidates           owners at New, ranked by interestingness
  GET  /api/leads/{cluster_id}   owner rollup + lead state + attempts
  PUT  /api/leads/{cluster_id}   set status and/or notes (validates ladder)

Every route resolves a tenant via ``current_tenant_id`` (stubbed to 1) and
goes through ``LeadStore`` / ``OwnersIndexService``, so every read and
write is tenant-scoped.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .auth import current_tenant_id
from .config import settings
from .db import get_db, init_db
from .lead_status import InvalidTransition
from .lead_store import LeadStore
from .owners_index_service import OwnersIndexService
from .schemas import CandidatesResponse, LeadDetail, LeadUpdate, OwnerSummary


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


def get_store(
    tenant_id: int = Depends(current_tenant_id),
    db: Session = Depends(get_db),
) -> Iterator[LeadStore]:
    yield LeadStore(db, tenant_id)


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "owners_indexed": owners_index.count}


@app.get("/api/candidates", response_model=CandidatesResponse)
def candidates(
    store: LeadStore = Depends(get_store),
    limit: int = Query(default=200, ge=1, le=2000),
) -> CandidatesResponse:
    rows = owners_index.list_candidates(store, limit=limit)
    return CandidatesResponse(
        count=len(rows),
        candidates=[OwnerSummary(**r) for r in rows],
    )


@app.get("/api/leads/{display_cluster_id}", response_model=LeadDetail)
def get_lead(display_cluster_id: str, store: LeadStore = Depends(get_store)) -> LeadDetail:
    view = owners_index.lead_view(store, display_cluster_id)
    if view is None:
        raise HTTPException(status_code=404, detail="owner not found in index")
    return _to_detail(view)


@app.put("/api/leads/{display_cluster_id}", response_model=LeadDetail)
def update_lead(
    display_cluster_id: str,
    body: LeadUpdate,
    store: LeadStore = Depends(get_store),
) -> LeadDetail:
    if owners_index.get_owner(display_cluster_id) is None:
        raise HTTPException(status_code=404, detail="owner not found in index")
    try:
        store.upsert(display_cluster_id, status=body.status, notes=body.notes)
    except InvalidTransition as exc:
        # 409 Conflict — the request is well-formed but illegal for this Lead's state.
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    view = owners_index.lead_view(store, display_cluster_id)
    assert view is not None  # owner existence checked above
    return _to_detail(view)


def _to_detail(view: dict) -> LeadDetail:
    owner = OwnerSummary(**{**view["owner"], "status": view["status"]})
    return LeadDetail(
        owner=owner,
        status=view["status"],
        notes=view["notes"],
        updated_at=view["updated_at"],
        attempts=view["attempts"],
    )
