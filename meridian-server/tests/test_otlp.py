import os
import time
import pytest

os.environ.setdefault("DB_PATH", ":memory:")   # will be set before app import

from httpx import AsyncClient, ASGITransport

# patch DB_PATH before importing app so it uses an in-memory DB per test run
os.environ["DB_PATH"] = f"/tmp/meridian_test_{os.getpid()}.db"

from server.main import app
from server.db import init_db

from opentelemetry.proto.collector.trace.v1 import trace_service_pb2
from opentelemetry.proto.common.v1 import common_pb2


def _make_otlp_payload(
    service: str = "test-service",
    trace_id: bytes = b"\xab" * 16,
    node_name: str = "researcher",
    cost_usd: float = 0.005,
    latency_ns: int = 500_000_000,    # 500 ms
) -> bytes:
    req = trace_service_pb2.ExportTraceServiceRequest()
    rs = req.resource_spans.add()
    rs.resource.attributes.append(
        common_pb2.KeyValue(
            key="service.name",
            value=common_pb2.AnyValue(string_value=service),
        )
    )
    ss = rs.scope_spans.add()

    # Derive unique-per-trace span IDs from the trace_id bytes.
    # XOR the second half so they're always distinct even for repeated-byte IDs.
    node_span_id = trace_id[:8]
    llm_span_id  = bytes(b ^ 0x01 for b in trace_id[:8])

    # langgraph.node span
    t_start = int(time.time() * 1e9)
    node_sp = ss.spans.add()
    node_sp.trace_id = trace_id
    node_sp.span_id  = node_span_id
    node_sp.name     = "langgraph.node"
    node_sp.start_time_unix_nano = t_start
    node_sp.end_time_unix_nano   = t_start + latency_ns
    node_sp.attributes.append(
        common_pb2.KeyValue(
            key="node.name",
            value=common_pb2.AnyValue(string_value=node_name),
        )
    )
    node_sp.attributes.append(
        common_pb2.KeyValue(
            key="node.latency_ms",
            value=common_pb2.AnyValue(double_value=latency_ns / 1e6),
        )
    )

    # llm.call span (child)
    llm_sp = ss.spans.add()
    llm_sp.trace_id       = trace_id
    llm_sp.span_id        = llm_span_id
    llm_sp.parent_span_id = node_span_id
    llm_sp.name           = "llm.call"
    llm_sp.start_time_unix_nano = t_start + 10_000_000
    llm_sp.end_time_unix_nano   = t_start + latency_ns - 10_000_000
    llm_sp.attributes.append(
        common_pb2.KeyValue(
            key="llm.model",
            value=common_pb2.AnyValue(string_value="gemini-2.0-flash"),
        )
    )
    llm_sp.attributes.append(
        common_pb2.KeyValue(
            key="llm.cost_usd",
            value=common_pb2.AnyValue(double_value=cost_usd),
        )
    )
    llm_sp.attributes.append(
        common_pb2.KeyValue(
            key="llm.input_tokens",
            value=common_pb2.AnyValue(int_value=100),
        )
    )
    llm_sp.attributes.append(
        common_pb2.KeyValue(
            key="llm.output_tokens",
            value=common_pb2.AnyValue(int_value=50),
        )
    )

    return req.SerializeToString()


@pytest.fixture(autouse=True)
async def setup_db():
    await init_db()
    yield


@pytest.mark.asyncio
async def test_otlp_endpoint_returns_200():
    payload = _make_otlp_payload()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/traces",
            content=payload,
            headers={"Content-Type": "application/x-protobuf"},
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_otlp_creates_run():
    trace_id = b"\xcc" * 16
    payload = _make_otlp_payload(trace_id=trace_id, service="svc-run-test")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/v1/traces",
            content=payload,
            headers={"Content-Type": "application/x-protobuf"},
        )
        resp = await client.get(f"/api/runs/{trace_id.hex()}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["service_name"] == "svc-run-test"
    assert data["model"] == "gemini-2.0-flash"


@pytest.mark.asyncio
async def test_otlp_span_count():
    trace_id = b"\xdd" * 16
    payload = _make_otlp_payload(trace_id=trace_id, service="svc-span-test")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/v1/traces",
            content=payload,
            headers={"Content-Type": "application/x-protobuf"},
        )
        resp = await client.get(f"/api/runs/{trace_id.hex()}/spans")
    assert resp.status_code == 200
    # 1 root (langgraph.node) with 1 child (llm.call)
    spans = resp.json()
    assert len(spans) == 1
    assert spans[0]["name"] == "langgraph.node"
    assert len(spans[0]["children"]) == 1
    assert spans[0]["children"][0]["name"] == "llm.call"


@pytest.mark.asyncio
async def test_otlp_cost_breakdown():
    trace_id = b"\xee" * 16
    payload = _make_otlp_payload(trace_id=trace_id, service="svc-cost-test", cost_usd=0.007)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/v1/traces",
            content=payload,
            headers={"Content-Type": "application/x-protobuf"},
        )
        resp = await client.get(f"/api/runs/{trace_id.hex()}/cost")
    assert resp.status_code == 200
    data = resp.json()
    assert abs(data["total_cost_usd"] - 0.007) < 1e-6
    assert len(data["breakdown"]) == 1


@pytest.mark.asyncio
async def test_empty_body_returns_200():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/traces",
            content=b"",
            headers={"Content-Type": "application/x-protobuf"},
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_runs_list_populated():
    trace_id = b"\xff" * 16
    payload = _make_otlp_payload(trace_id=trace_id, service="svc-list-test")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/v1/traces",
            content=payload,
            headers={"Content-Type": "application/x-protobuf"},
        )
        resp = await client.get("/api/runs")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    ids = [r["id"] for r in data["items"]]
    assert trace_id.hex() in ids
