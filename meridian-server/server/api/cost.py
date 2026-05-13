from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, HTTPException

from server import db
from server.models import CostResponse, NodeCost

router = APIRouter(prefix="/runs", tags=["cost"])


@router.get("/{run_id}/cost", response_model=CostResponse)
async def get_cost(run_id: str):
    row = await db.get_run(run_id)
    if not row:
        raise HTTPException(status_code=404, detail="Run not found")

    spans = await db.get_spans_for_run(run_id)
    llm_spans = [s for s in spans if s["name"] == "llm.call"]

    # Group by the parent node name (walk up one level) or use "unknown"
    span_by_id = {s["id"]: s for s in spans}
    node_stats: dict[str, dict] = defaultdict(
        lambda: {"cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0, "call_count": 0}
    )

    for s in llm_spans:
        parent = span_by_id.get(s.get("parent_id") or "")
        node_name = (
            parent["attributes"].get("node.name", parent["name"])
            if parent
            else "direct"
        )
        attrs = s["attributes"]
        node_stats[node_name]["cost_usd"]      += float(attrs.get("llm.cost_usd",      0.0))
        node_stats[node_name]["input_tokens"]  += int(attrs.get("llm.input_tokens",   0))
        node_stats[node_name]["output_tokens"] += int(attrs.get("llm.output_tokens",  0))
        node_stats[node_name]["call_count"]    += 1

    total_cost   = sum(v["cost_usd"]      for v in node_stats.values())
    total_input  = sum(v["input_tokens"]  for v in node_stats.values())
    total_output = sum(v["output_tokens"] for v in node_stats.values())

    breakdown = [
        NodeCost(node_name=name, **stats)
        for name, stats in sorted(
            node_stats.items(), key=lambda kv: kv[1]["cost_usd"], reverse=True
        )
    ]

    return CostResponse(
        run_id=run_id,
        total_cost_usd=total_cost,
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        breakdown=breakdown,
    )
