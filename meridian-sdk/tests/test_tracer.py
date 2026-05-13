import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry import trace as otel_trace

from meridian.tracer import setup_tracer, get_tracer


def _make_in_memory_provider(service_name: str) -> tuple[TracerProvider, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = setup_tracer(service_name)
    # Replace the batch processor with a sync in-memory one for tests
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider, exporter


def test_setup_tracer_returns_provider():
    provider = setup_tracer("test-service")
    assert isinstance(provider, TracerProvider)


def test_get_tracer_after_setup():
    setup_tracer("test-service-2")
    t = get_tracer("test")
    assert t is not None


def test_get_tracer_before_setup_raises():
    import meridian.tracer as mod
    original = mod._provider
    mod._provider = None
    with pytest.raises(RuntimeError, match="instrument"):
        get_tracer()
    mod._provider = original


def test_span_created_and_recorded():
    _, exporter = _make_in_memory_provider("span-test")
    tracer = get_tracer("meridian")
    with tracer.start_as_current_span("test.span") as span:
        span.set_attribute("foo", "bar")

    spans = exporter.get_finished_spans()
    names = [s.name for s in spans]
    assert "test.span" in names
