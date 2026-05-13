from __future__ import annotations

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

_provider: TracerProvider | None = None


def setup_tracer(service_name: str, otlp_endpoint: str | None = None) -> TracerProvider:
    global _provider

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)

    if otlp_endpoint:
        exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
    else:
        exporter = ConsoleSpanExporter()

    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _provider = provider
    return provider


def get_tracer(name: str = "meridian") -> trace.Tracer:
    if _provider is None:
        raise RuntimeError("Call instrument() before using the tracer.")
    return _provider.get_tracer(name)
