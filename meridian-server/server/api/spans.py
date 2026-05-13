from __future__ import annotations

from fastapi import APIRouter, HTTPException

from server import db
from server.models import SpanModel

router = APIRouter(prefix="/runs", tags=["spans"])


def _build_tree(spans: list[dict]) -> list[SpanModel]:
    """Convert a flat span list into a nested tree rooted at top-level spans."""
    nodes: dict[str, SpanModel] = {
        s["id"]: SpanModel(**s) for s in spans
    }
    roots: list[SpanModel] = []

    for model in nodes.values():
        if model.parent_id and model.parent_id in nodes:
            nodes[model.parent_id].children.append(model)
        else:
            roots.append(model)

    return roots


@router.get("/{run_id}/spans", response_model=list[SpanModel])
async def get_spans(run_id: str):
    row = await db.get_run(run_id)
    if not row:
        raise HTTPException(status_code=404, detail="Run not found")
    spans = await db.get_spans_for_run(run_id)
    return _build_tree(spans)
