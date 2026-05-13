from __future__ import annotations

import os
import time
import uuid

from server.alerts import rules as rule_module
from server.alerts.websocket import manager
from server import db

_BUDGET_USD   = float(os.getenv("BUDGET_THRESHOLD_USD", "0.10"))
_LATENCY_MS   = float(os.getenv("LATENCY_BASELINE_MS",  "2000"))

_ALL_RULES = [
    lambda spans: rule_module.loop_rule(spans),
    lambda spans: rule_module.budget_rule(spans, _BUDGET_USD),
    lambda spans: rule_module.latency_spike_rule(spans, _LATENCY_MS),
]


async def evaluate_run(run_id: str, spans: list[dict]) -> None:
    """Run all alert rules against the span list; persist and broadcast any hits."""
    for rule_fn in _ALL_RULES:
        result = rule_fn(spans)
        if result is None:
            continue

        alert = {
            "id":        str(uuid.uuid4()),
            "run_id":    run_id,
            "rule_name": result["rule_name"],
            "severity":  result["severity"],
            "message":   result["message"],
            "fired_at":  time.time(),
        }
        inserted = await db.insert_alert(alert)
        if inserted:
            await manager.broadcast(alert)
