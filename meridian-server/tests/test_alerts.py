import pytest
from server.alerts.rules import loop_rule, budget_rule, latency_spike_rule


def _node_span(node_name: str) -> dict:
    return {"name": "langgraph.node", "attributes": {"node.name": node_name}, "latency_ms": 50.0}


def _llm_span(cost: float, latency_ms: float = 100.0) -> dict:
    return {
        "name": "llm.call",
        "attributes": {"llm.cost_usd": cost, "llm.input_tokens": 100, "llm.output_tokens": 50},
        "latency_ms": latency_ms,
    }


# ── loop_rule ───────────────────────────────────────────────────────────────

def test_loop_rule_no_loop_exactly_five():
    spans = [_node_span("a") for _ in range(5)]
    assert loop_rule(spans) is None


def test_loop_rule_fires_at_six():
    spans = [_node_span("a") for _ in range(6)]
    result = loop_rule(spans)
    assert result is not None
    assert result["rule_name"] == "loop_detected"
    assert result["severity"] == "warning"
    assert "a" in result["message"]


def test_loop_rule_different_nodes_no_fire():
    spans = [_node_span(f"node_{i}") for i in range(10)]
    assert loop_rule(spans) is None


def test_loop_rule_ignores_llm_spans():
    spans = [_llm_span(0.01) for _ in range(10)]
    assert loop_rule(spans) is None


def test_loop_rule_detects_correct_node():
    spans = [_node_span("a")] * 6 + [_node_span("b")] * 3
    result = loop_rule(spans)
    assert result is not None
    assert "a" in result["message"]


# ── budget_rule ─────────────────────────────────────────────────────────────

def test_budget_rule_under_threshold():
    spans = [_llm_span(0.01) for _ in range(5)]   # total = 0.05
    assert budget_rule(spans, threshold_usd=0.10) is None


def test_budget_rule_fires_at_threshold():
    spans = [_llm_span(0.05) for _ in range(2)]   # total = 0.10
    result = budget_rule(spans, threshold_usd=0.10)
    assert result is not None
    assert result["rule_name"] == "budget_exceeded"
    assert result["severity"] == "error"


def test_budget_rule_fires_over_threshold():
    spans = [_llm_span(0.06) for _ in range(2)]   # total = 0.12
    result = budget_rule(spans, threshold_usd=0.10)
    assert result is not None


def test_budget_rule_ignores_node_spans():
    spans = [_node_span("a") for _ in range(100)]
    assert budget_rule(spans, threshold_usd=0.01) is None


def test_budget_rule_custom_threshold():
    spans = [_llm_span(0.005)]                     # total = 0.005
    assert budget_rule(spans, threshold_usd=0.01) is None
    assert budget_rule(spans, threshold_usd=0.004) is not None


# ── latency_spike_rule ──────────────────────────────────────────────────────

def test_latency_spike_no_spike():
    spans = [{"name": "langgraph.node", "latency_ms": 500.0, "attributes": {}}]
    assert latency_spike_rule(spans, baseline_ms=2000.0) is None


def test_latency_spike_fires():
    spans = [{"name": "langgraph.node", "latency_ms": 3000.0, "attributes": {}}]
    result = latency_spike_rule(spans, baseline_ms=2000.0)
    assert result is not None
    assert result["rule_name"] == "latency_spike"
    assert result["severity"] == "warning"
    assert "3000" in result["message"]


def test_latency_spike_fires_on_llm_span():
    spans = [_llm_span(0.01, latency_ms=5000.0)]
    result = latency_spike_rule(spans, baseline_ms=2000.0)
    assert result is not None


def test_latency_spike_exactly_at_baseline_no_fire():
    spans = [{"name": "langgraph.node", "latency_ms": 2000.0, "attributes": {}}]
    assert latency_spike_rule(spans, baseline_ms=2000.0) is None


def test_latency_spike_empty_spans():
    assert latency_spike_rule([], baseline_ms=2000.0) is None
