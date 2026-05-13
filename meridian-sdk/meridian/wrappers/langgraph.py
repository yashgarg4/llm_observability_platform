from __future__ import annotations

import asyncio
import functools
import time
from typing import Any, Callable

import wrapt
from opentelemetry import trace
from opentelemetry.trace import StatusCode


def _node_keys(state: Any) -> list[str]:
    if isinstance(state, dict):
        return list(state.keys())
    if hasattr(state, "__dict__"):
        return list(vars(state).keys())
    return []


def _make_sync_wrapper(fn: Callable, node_name: str) -> Callable:
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        tracer = trace.get_tracer("meridian")
        input_state = args[0] if args else kwargs.get("state")
        with tracer.start_as_current_span("langgraph.node") as span:
            span.set_attribute("node.name", node_name)
            span.set_attribute("node.input_state_keys", str(_node_keys(input_state)))
            t0 = time.perf_counter()
            try:
                result = fn(*args, **kwargs)
            except Exception as exc:
                span.set_attribute("node.error", str(exc))
                span.set_status(StatusCode.ERROR, str(exc))
                span.record_exception(exc)
                raise
            finally:
                span.set_attribute("node.latency_ms", round((time.perf_counter() - t0) * 1000, 2))
            span.set_attribute("node.output_state_keys", str(_node_keys(result)))
            span.set_status(StatusCode.OK)
        return result
    return wrapper


def _make_async_wrapper(fn: Callable, node_name: str) -> Callable:
    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        tracer = trace.get_tracer("meridian")
        input_state = args[0] if args else kwargs.get("state")
        with tracer.start_as_current_span("langgraph.node") as span:
            span.set_attribute("node.name", node_name)
            span.set_attribute("node.input_state_keys", str(_node_keys(input_state)))
            t0 = time.perf_counter()
            try:
                result = await fn(*args, **kwargs)
            except Exception as exc:
                span.set_attribute("node.error", str(exc))
                span.set_status(StatusCode.ERROR, str(exc))
                span.record_exception(exc)
                raise
            finally:
                span.set_attribute("node.latency_ms", round((time.perf_counter() - t0) * 1000, 2))
            span.set_attribute("node.output_state_keys", str(_node_keys(result)))
            span.set_status(StatusCode.OK)
        return result
    return wrapper


def _compile_wrapper(original, instance, args, kwargs):
    """Intercept StateGraph.compile() to instrument each node's RunnableCallable."""
    try:
        from langgraph._internal._runnable import RunnableCallable
    except ImportError:
        return original(*args, **kwargs)

    nodes: dict = getattr(instance, "nodes", {})
    for name, spec in nodes.items():
        runnable = getattr(spec, "runnable", None)
        if not isinstance(runnable, RunnableCallable):
            continue

        original_func = runnable.func
        original_afunc = runnable.afunc

        if original_func is not None:
            runnable.func = _make_sync_wrapper(original_func, name)

        if original_afunc is not None:
            # afunc may be a partial(run_in_executor, None, sync_fn) — replace
            # with a true async wrapper around the already-instrumented sync fn
            # OR wrap the original coroutine function directly.
            if asyncio.iscoroutinefunction(original_afunc):
                runnable.afunc = _make_async_wrapper(original_afunc, name)
            else:
                # It's a thread-executor partial — the sync wrapper already
                # instruments it; rebuild the partial over the wrapped func.
                try:
                    from langgraph._internal._runnable import run_in_executor
                    if original_func is not None:
                        runnable.afunc = functools.partial(run_in_executor, None, runnable.func)
                except ImportError:
                    pass

    return original(*args, **kwargs)


def patch_langgraph() -> None:
    try:
        from langgraph.graph import StateGraph
    except ImportError:
        return

    if not getattr(StateGraph, "_meridian_patched", False):
        wrapt.wrap_function_wrapper(StateGraph, "compile", _compile_wrapper)
        StateGraph._meridian_patched = True
