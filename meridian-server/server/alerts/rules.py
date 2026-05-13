from __future__ import annotations

from collections import Counter


def loop_rule(spans: list[dict]) -> dict | None:
    """Fire if any LangGraph node executes more than 5 times in a run."""
    counts = Counter(
        s["attributes"].get("node.name", "")
        for s in spans
        if s.get("name") == "langgraph.node" and s["attributes"].get("node.name")
    )
    for node, count in counts.items():
        if count > 5:
            return {
                "rule_name": "loop_detected",
                "severity": "warning",
                "message": f"Node '{node}' executed {count} times — possible infinite loop",
            }
    return None


def budget_rule(spans: list[dict], threshold_usd: float = 0.10) -> dict | None:
    """Fire if total LLM cost for the run exceeds threshold_usd."""
    total = sum(
        float(s["attributes"].get("llm.cost_usd", 0.0))
        for s in spans
        if s.get("name") == "llm.call"
    )
    if total >= threshold_usd:
        return {
            "rule_name": "budget_exceeded",
            "severity": "error",
            "message": (
                f"Run cost ${total:.4f} exceeds budget threshold ${threshold_usd:.4f}"
            ),
        }
    return None


def latency_spike_rule(spans: list[dict], baseline_ms: float = 2000.0) -> dict | None:
    """Fire if any single span latency exceeds baseline_ms."""
    for span in spans:
        latency = float(span.get("latency_ms") or 0.0)
        if latency > baseline_ms:
            return {
                "rule_name": "latency_spike",
                "severity": "warning",
                "message": (
                    f"Span '{span.get('name')}' took {latency:.0f} ms "
                    f"(threshold: {baseline_ms:.0f} ms)"
                ),
            }
    return None
