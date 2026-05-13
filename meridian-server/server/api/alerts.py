from __future__ import annotations

from fastapi import APIRouter, Query

from server import db
from server.models import AlertModel

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertModel])
async def list_alerts(
    limit: int  = Query(100, ge=1, le=500),
    offset: int = Query(0,   ge=0),
    run_id: str = Query(None),
):
    rows = await db.get_alerts(limit=limit, offset=offset, run_id=run_id)
    return [AlertModel(**r) for r in rows]
