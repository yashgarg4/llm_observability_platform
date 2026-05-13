from __future__ import annotations

import json
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

import aiosqlite

_DB_PATH: Path = Path(os.getenv("DB_PATH", "./meridian.db"))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id              TEXT PRIMARY KEY,
    service_name    TEXT NOT NULL,
    model           TEXT,
    start_time      REAL,
    end_time        REAL,
    total_cost_usd  REAL DEFAULT 0.0,
    total_tokens    INTEGER DEFAULT 0,
    status          TEXT DEFAULT 'ok'
);

CREATE TABLE IF NOT EXISTS spans (
    id          TEXT PRIMARY KEY,
    run_id      TEXT NOT NULL,
    name        TEXT NOT NULL,
    parent_id   TEXT,
    start_time  REAL,
    end_time    REAL,
    latency_ms  REAL,
    attributes  TEXT DEFAULT '{}',
    error       TEXT,
    FOREIGN KEY (run_id) REFERENCES runs(id)
);

CREATE INDEX IF NOT EXISTS idx_spans_run_id ON spans(run_id);
CREATE INDEX IF NOT EXISTS idx_runs_service  ON runs(service_name);
CREATE INDEX IF NOT EXISTS idx_runs_start    ON runs(start_time);

CREATE TABLE IF NOT EXISTS alerts (
    id          TEXT PRIMARY KEY,
    run_id      TEXT NOT NULL,
    rule_name   TEXT NOT NULL,
    severity    TEXT NOT NULL,
    message     TEXT NOT NULL,
    fired_at    REAL NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(id)
);

CREATE INDEX IF NOT EXISTS idx_alerts_run_id  ON alerts(run_id);
CREATE INDEX IF NOT EXISTS idx_alerts_fired   ON alerts(fired_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_alerts_run_rule ON alerts(run_id, rule_name);
"""


@asynccontextmanager
async def get_db() -> AsyncIterator[aiosqlite.Connection]:
    async with aiosqlite.connect(_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")
        yield db


async def init_db() -> None:
    async with get_db() as db:
        await db.executescript(_SCHEMA)
        await db.commit()


async def upsert_run(
    run_id: str,
    service_name: str,
    spans: list[dict],
) -> None:
    start_time = min((s["start_time"] for s in spans), default=0.0)
    end_time   = max((s["end_time"]   for s in spans), default=0.0)
    total_cost = sum(
        s["attributes"].get("llm.cost_usd", 0.0) for s in spans
    )
    total_tokens = sum(
        s["attributes"].get("llm.input_tokens", 0)
        + s["attributes"].get("llm.output_tokens", 0)
        for s in spans
    )
    model = next(
        (s["attributes"]["llm.model"] for s in spans if "llm.model" in s["attributes"]),
        None,
    )
    status = "error" if any(s.get("error") for s in spans) else "ok"

    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO runs (id, service_name, model, start_time, end_time,
                              total_cost_usd, total_tokens, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                end_time       = excluded.end_time,
                total_cost_usd = excluded.total_cost_usd,
                total_tokens   = excluded.total_tokens,
                status         = excluded.status,
                model          = COALESCE(excluded.model, runs.model)
            """,
            (run_id, service_name, model, start_time, end_time,
             total_cost, total_tokens, status),
        )
        await db.commit()


async def insert_span(span: dict) -> None:
    async with get_db() as db:
        await db.execute(
            """
            INSERT OR IGNORE INTO spans
                (id, run_id, name, parent_id, start_time, end_time,
                 latency_ms, attributes, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                span["id"],
                span["run_id"],
                span["name"],
                span.get("parent_id"),
                span["start_time"],
                span["end_time"],
                span["latency_ms"],
                json.dumps(span.get("attributes", {})),
                span.get("error"),
            ),
        )
        await db.commit()


async def insert_spans_bulk(spans: list[dict]) -> None:
    if not spans:
        return
    async with get_db() as db:
        await db.executemany(
            """
            INSERT OR IGNORE INTO spans
                (id, run_id, name, parent_id, start_time, end_time,
                 latency_ms, attributes, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    s["id"], s["run_id"], s["name"], s.get("parent_id"),
                    s["start_time"], s["end_time"], s["latency_ms"],
                    json.dumps(s.get("attributes", {})), s.get("error"),
                )
                for s in spans
            ],
        )
        await db.commit()


async def insert_alert(alert: dict) -> bool:
    """Insert alert. Returns True if inserted, False if already exists (dedup)."""
    async with get_db() as db:
        cur = await db.execute(
            """
            INSERT OR IGNORE INTO alerts (id, run_id, rule_name, severity, message, fired_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                alert.get("id", str(uuid.uuid4())),
                alert["run_id"],
                alert["rule_name"],
                alert["severity"],
                alert["message"],
                alert["fired_at"],
            ),
        )
        await db.commit()
        return cur.rowcount > 0


async def recompute_run_totals(run_id: str) -> None:
    """Recompute cost/token/model totals from ALL stored spans for a run.

    Called after each OTLP batch so later batches (e.g. parent node span
    arriving after the llm.call span) don't overwrite totals with zeros.
    """
    async with get_db() as db:
        async with db.execute(
            """
            SELECT
                COALESCE(SUM(CAST(json_extract(attributes,'$.llm.cost_usd') AS REAL)), 0) AS total_cost,
                COALESCE(SUM(
                    COALESCE(CAST(json_extract(attributes,'$.llm.input_tokens')  AS INT), 0) +
                    COALESCE(CAST(json_extract(attributes,'$.llm.output_tokens') AS INT), 0)
                ), 0) AS total_tokens,
                MAX(json_extract(attributes,'$.llm.model')) AS model
            FROM spans
            WHERE run_id = ? AND name = 'llm.call'
            """,
            (run_id,),
        ) as cur:
            row = await cur.fetchone()
        if row:
            await db.execute(
                """
                UPDATE runs
                SET total_cost_usd = ?,
                    total_tokens   = ?,
                    model          = COALESCE(?, model)
                WHERE id = ?
                """,
                (row["total_cost"], row["total_tokens"], row["model"], run_id),
            )
            await db.commit()


async def get_spans_for_run(run_id: str) -> list[dict]:
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM spans WHERE run_id = ? ORDER BY start_time", (run_id,)
        ) as cur:
            rows = await cur.fetchall()
    return [
        {**dict(row), "attributes": json.loads(row["attributes"] or "{}")}
        for row in rows
    ]


async def get_runs(
    limit: int = 50,
    offset: int = 0,
    service_name: str | None = None,
    model: str | None = None,
    since: float | None = None,
    until: float | None = None,
) -> list[dict]:
    conditions: list[str] = []
    params: list[Any] = []

    if service_name:
        conditions.append("service_name = ?")
        params.append(service_name)
    if model:
        conditions.append("model = ?")
        params.append(model)
    if since:
        conditions.append("start_time >= ?")
        params.append(since)
    if until:
        conditions.append("start_time <= ?")
        params.append(until)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    params += [limit, offset]

    async with get_db() as db:
        async with db.execute(
            f"SELECT * FROM runs {where} ORDER BY start_time DESC LIMIT ? OFFSET ?",
            params,
        ) as cur:
            rows = await cur.fetchall()
    return [dict(row) for row in rows]


async def get_run(run_id: str) -> dict | None:
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM runs WHERE id = ?", (run_id,)
        ) as cur:
            row = await cur.fetchone()
    return dict(row) if row else None


async def get_regression(
    service_name: str | None = None,
    bucket: str = "day",
    since: float | None = None,
    until: float | None = None,
    limit: int = 30,
) -> list[dict]:
    fmt = "%Y-%m-%dT%H" if bucket == "hour" else "%Y-%m-%d"
    conditions: list[str] = []
    params: list[Any] = []

    if service_name:
        conditions.append("service_name = ?")
        params.append(service_name)
    if since:
        conditions.append("start_time >= ?")
        params.append(since)
    if until:
        conditions.append("start_time <= ?")
        params.append(until)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    params.append(limit)

    sql = f"""
        SELECT
            strftime('{fmt}', datetime(start_time, 'unixepoch')) AS bucket,
            service_name,
            COUNT(*) AS run_count,
            AVG((end_time - start_time) * 1000)  AS avg_latency_ms,
            MAX((end_time - start_time) * 1000)  AS max_latency_ms,
            AVG(total_cost_usd)                  AS avg_cost_usd,
            AVG(total_tokens)                    AS avg_tokens,
            SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS error_rate
        FROM runs
        {where}
        GROUP BY bucket, service_name
        ORDER BY bucket DESC
        LIMIT ?
    """

    async with get_db() as db:
        async with db.execute(sql, params) as cur:
            rows = await cur.fetchall()
    return [dict(row) for row in rows]


async def get_alerts(
    limit: int = 100,
    offset: int = 0,
    run_id: str | None = None,
) -> list[dict]:
    if run_id:
        sql = "SELECT * FROM alerts WHERE run_id = ? ORDER BY fired_at DESC LIMIT ? OFFSET ?"
        params = [run_id, limit, offset]
    else:
        sql = "SELECT * FROM alerts ORDER BY fired_at DESC LIMIT ? OFFSET ?"
        params = [limit, offset]

    async with get_db() as db:
        async with db.execute(sql, params) as cur:
            rows = await cur.fetchall()
    return [dict(row) for row in rows]
