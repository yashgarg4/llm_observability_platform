"""FastAPI middleware for tracing inbound HTTP requests via OpenTelemetry."""
from __future__ import annotations

import time

from opentelemetry import trace
from opentelemetry.trace import StatusCode


class MeridianMiddleware:
    """ASGI middleware that creates a root span for every HTTP request."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        tracer = trace.get_tracer("meridian")
        method = scope.get("method", "GET")
        path = scope.get("path", "/")

        with tracer.start_as_current_span(f"http.request") as span:
            span.set_attribute("http.method", method)
            span.set_attribute("http.path", path)
            t0 = time.perf_counter()
            status_code = 500

            async def send_wrapper(message):
                nonlocal status_code
                if message["type"] == "http.response.start":
                    status_code = message.get("status", 500)
                await send(message)

            try:
                await self.app(scope, receive, send_wrapper)
                span.set_attribute("http.status_code", status_code)
                span.set_status(StatusCode.OK if status_code < 400 else StatusCode.ERROR)
            except Exception as exc:
                span.set_status(StatusCode.ERROR, str(exc))
                span.record_exception(exc)
                raise
            finally:
                span.set_attribute("http.latency_ms", round((time.perf_counter() - t0) * 1000, 2))
