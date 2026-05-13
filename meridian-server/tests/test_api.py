import os
import time
import uuid
import pytest

os.environ["DB_PATH"] = f"/tmp/meridian_api_test_{os.getpid()}.db"

from httpx import AsyncClient, ASGITransport
from server.main import app
from server.db import init_db, upsert_run, insert_spans_bulk, insert_alert


async def _seed_run(run_id: str, service: str = "svc-a", cost: float = 0.01):
    spans = [
        {
            "id": str(uuid.uuid4()),
            "run_id": run_id,
            "name": "langgraph.node",
            "parent_id": None,
            "start_time": time.time(),
            "end_time": time.time() + 0.5,
            "latency_ms": 500.0,
            "attributes": {"node.name": "node_a"},
            "error": None,
        },
        {
            "id": str(uuid.uuid4()),
            "run_id": run_id,
            "name": "llm.call",
            "parent_id": None,
            "start_time": time.time() + 0.1,
            "end_time": time.time() + 0.4,
            "latency_ms": 300.0,
            "attributes": {
                "llm.model": "gemini-2.0-flash",
                "llm.cost_usd": cost,
                "llm.input_tokens": 100,
                "llm.output_tokens": 50,
            },
            "error": None,
        },
    ]
    await upsert_run(run_id, service, spans)
    await insert_spans_bulk(spans)
    return spans


@pytest.fixture(autouse=True)
async def setup_db():
    await init_db()
    yield


@pytest.mark.asyncio
async def test_get_run_404():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/runs/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_run_ok():
    run_id = str(uuid.uuid4())
    await _seed_run(run_id)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/runs/{run_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == run_id
    assert data["service_name"] == "svc-a"
    assert data["model"] == "gemini-2.0-flash"


@pytest.mark.asyncio
async def test_list_runs_filter_by_service():
    run_id = str(uuid.uuid4())
    await _seed_run(run_id, service="unique-svc-xyz")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/runs", params={"service_name": "unique-svc-xyz"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert all(r["service_name"] == "unique-svc-xyz" for r in data["items"])


@pytest.mark.asyncio
async def test_get_spans_flat_then_nested():
    run_id = str(uuid.uuid4())
    parent_id = str(uuid.uuid4())
    child_id  = str(uuid.uuid4())
    spans = [
        {
            "id": parent_id, "run_id": run_id, "name": "langgraph.node",
            "parent_id": None, "start_time": 1.0, "end_time": 1.5,
            "latency_ms": 500.0, "attributes": {"node.name": "root"}, "error": None,
        },
        {
            "id": child_id, "run_id": run_id, "name": "llm.call",
            "parent_id": parent_id, "start_time": 1.1, "end_time": 1.4,
            "latency_ms": 300.0,
            "attributes": {"llm.cost_usd": 0.01, "llm.input_tokens": 50, "llm.output_tokens": 20},
            "error": None,
        },
    ]
    await upsert_run(run_id, "svc-nest", spans)
    await insert_spans_bulk(spans)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/runs/{run_id}/spans")
    assert resp.status_code == 200
    tree = resp.json()
    assert len(tree) == 1
    assert tree[0]["name"] == "langgraph.node"
    assert len(tree[0]["children"]) == 1
    assert tree[0]["children"][0]["name"] == "llm.call"


@pytest.mark.asyncio
async def test_cost_breakdown():
    run_id = str(uuid.uuid4())
    await _seed_run(run_id, cost=0.042)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/runs/{run_id}/cost")
    assert resp.status_code == 200
    data = resp.json()
    assert abs(data["total_cost_usd"] - 0.042) < 1e-6
    assert data["total_input_tokens"] == 100
    assert data["total_output_tokens"] == 50
    assert len(data["breakdown"]) >= 1


@pytest.mark.asyncio
async def test_alerts_empty():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/alerts")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_alerts_returns_seeded():
    run_id = str(uuid.uuid4())
    await _seed_run(run_id)
    alert = {
        "id": str(uuid.uuid4()),
        "run_id": run_id,
        "rule_name": "budget_exceeded",
        "severity": "error",
        "message": "test alert",
        "fired_at": time.time(),
    }
    await insert_alert(alert)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/alerts", params={"run_id": run_id})
    assert resp.status_code == 200
    items = resp.json()
    assert any(a["rule_name"] == "budget_exceeded" for a in items)


@pytest.mark.asyncio
async def test_health():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
