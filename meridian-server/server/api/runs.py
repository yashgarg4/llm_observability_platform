from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from server import db
from server.models import PaginatedRuns, RunModel

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("", response_model=PaginatedRuns)
async def list_runs(
    limit: int        = Query(50,  ge=1, le=200),
    offset: int       = Query(0,   ge=0),
    service_name: str = Query(None),
    model: str        = Query(None),
    since: float      = Query(None, description="Unix timestamp lower bound"),
    until: float      = Query(None, description="Unix timestamp upper bound"),
):
    rows = await db.get_runs(
        limit=limit,
        offset=offset,
        service_name=service_name,
        model=model,
        since=since,
        until=until,
    )
    # Total count with same filters (no pagination)
    all_rows = await db.get_runs(
        limit=10_000,
        offset=0,
        service_name=service_name,
        model=model,
        since=since,
        until=until,
    )
    return PaginatedRuns(
        items=[RunModel(**r) for r in rows],
        total=len(all_rows),
        limit=limit,
        offset=offset,
    )


@router.get("/{run_id}", response_model=RunModel)
async def get_run(run_id: str):
    row = await db.get_run(run_id)
    if not row:
        raise HTTPException(status_code=404, detail="Run not found")
    return RunModel(**row)
