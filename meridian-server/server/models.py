from __future__ import annotations

from pydantic import BaseModel, Field


class SpanModel(BaseModel):
    id: str
    run_id: str
    name: str
    parent_id: str | None = None
    start_time: float
    end_time: float
    latency_ms: float
    attributes: dict = Field(default_factory=dict)
    error: str | None = None
    children: list["SpanModel"] = Field(default_factory=list)


class RunModel(BaseModel):
    id: str
    service_name: str
    model: str | None = None
    start_time: float
    end_time: float | None = None
    total_cost_usd: float = 0.0
    total_tokens: int = 0
    status: str = "ok"


class AlertModel(BaseModel):
    id: str
    run_id: str
    rule_name: str
    severity: str
    message: str
    fired_at: float


class NodeCost(BaseModel):
    node_name: str
    cost_usd: float
    input_tokens: int
    output_tokens: int
    call_count: int


class CostResponse(BaseModel):
    run_id: str
    total_cost_usd: float
    total_input_tokens: int
    total_output_tokens: int
    breakdown: list[NodeCost]


class PaginatedRuns(BaseModel):
    items: list[RunModel]
    total: int
    limit: int
    offset: int
