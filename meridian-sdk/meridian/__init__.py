from __future__ import annotations

from meridian.tracer import setup_tracer
from meridian.wrappers import patch_chatgoogle, patch_langgraph

__version__ = "0.1.0"
__all__ = ["instrument", "shutdown"]


def shutdown() -> None:
    """Flush and shut down the tracer provider (call before process exit)."""
    from meridian import tracer as _mod
    if _mod._provider is not None:
        _mod._provider.force_flush()
        _mod._provider.shutdown()


def instrument(service_name: str, otlp_endpoint: str | None = None) -> None:
    """Instrument a LangGraph agent with OpenTelemetry tracing.

    Usage::

        from meridian import instrument
        instrument("my-service")                                  # console
        instrument("my-service", "http://localhost:8001/v1/traces")  # OTLP
    """
    setup_tracer(service_name, otlp_endpoint)
    patch_chatgoogle()
    patch_langgraph()
