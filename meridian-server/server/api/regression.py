from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel

from server import db

router = APIRouter()


class RegressionPoint(BaseModel):
    bucket: str
    service_name: str
    run_count: int
    avg_latency_ms: float | None
    max_latency_ms: float | None
    avg_cost_usd: float | None
    avg_tokens: float | None
    error_rate: float


@router.get("/regression", response_model=list[RegressionPoint])
async def get_regression(
    service_name: str | None = Query(None),
    bucket: str = Query("day"),
    since: float | None = Query(None),
    until: float | None = Query(None),
    limit: int = Query(30, ge=1, le=200),
) -> list[RegressionPoint]:
    if bucket not in ("hour", "day"):
        bucket = "day"
    rows = await db.get_regression(
        service_name=service_name,
        bucket=bucket,
        since=since,
        until=until,
        limit=limit,
    )
    return [RegressionPoint(**r) for r in rows]
