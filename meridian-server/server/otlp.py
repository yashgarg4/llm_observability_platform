from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, Response
from opentelemetry.proto.collector.trace.v1 import trace_service_pb2
from opentelemetry.proto.common.v1 import common_pb2

from server import db
from server.alerts.engine import evaluate_run

router = APIRouter()


def _anyvalue(v: common_pb2.AnyValue) -> Any:
    kind = v.WhichOneof("value")
    if kind == "string_value":  return v.string_value
    if kind == "int_value":     return v.int_value
    if kind == "double_value":  return v.double_value
    if kind == "bool_value":    return v.bool_value
    if kind == "bytes_value":   return v.bytes_value.hex()
    if kind == "array_value":
        return [_anyvalue(item) for item in v.array_value.values]
    if kind == "kvlist_value":
        return {kv.key: _anyvalue(kv.value) for kv in v.kvlist_value.values}
    return None


def _attrs(kvlist) -> dict:
    return {kv.key: _anyvalue(kv.value) for kv in kvlist}


@router.post("/v1/traces", status_code=200)
async def receive_traces(request: Request) -> Response:
    body = await request.body()
    if not body:
        return Response(status_code=200)

    req = trace_service_pb2.ExportTraceServiceRequest()
    req.ParseFromString(body)

    # Group parsed spans by trace_id
    by_trace: dict[str, dict] = {}          # trace_id → {service_name, spans[]}
    span_dicts: list[dict] = []

    for rs in req.resource_spans:
        service_name = _attrs(rs.resource.attributes).get("service.name", "unknown")

        for ss in rs.scope_spans:
            for sp in ss.spans:
                trace_id  = sp.trace_id.hex()
                span_id   = sp.span_id.hex()
                parent_id = sp.parent_span_id.hex() if sp.parent_span_id else None

                start_s    = sp.start_time_unix_nano / 1e9
                end_s      = sp.end_time_unix_nano   / 1e9
                latency_ms = (end_s - start_s) * 1000

                attrs = _attrs(sp.attributes)

                error: str | None = None
                if sp.status.code == 2:          # STATUS_CODE_ERROR
                    error = sp.status.message or "error"

                span_dict = {
                    "id":         span_id,
                    "run_id":     trace_id,
                    "name":       sp.name,
                    "parent_id":  parent_id,
                    "start_time": start_s,
                    "end_time":   end_s,
                    "latency_ms": round(latency_ms, 3),
                    "attributes": attrs,
                    "error":      error,
                }
                span_dicts.append(span_dict)

                if trace_id not in by_trace:
                    by_trace[trace_id] = {"service_name": service_name, "spans": []}
                by_trace[trace_id]["spans"].append(span_dict)

    # Runs must exist before spans (FK constraint) — upsert runs first
    for trace_id, info in by_trace.items():
        await db.upsert_run(trace_id, info["service_name"], info["spans"])

    await db.insert_spans_bulk(span_dicts)

    # Recompute run totals from all DB spans so later batches (e.g. a parent
    # node span arriving after the llm.call span) don't overwrite cost with 0.
    for trace_id in by_trace:
        await db.recompute_run_totals(trace_id)

    # Evaluate alerts after all data is persisted
    for trace_id in by_trace:
        all_spans = await db.get_spans_for_run(trace_id)
        await evaluate_run(trace_id, all_spans)

    return Response(status_code=200)
