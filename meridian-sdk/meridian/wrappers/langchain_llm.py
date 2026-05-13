from __future__ import annotations

import time
from typing import Any

import wrapt
from opentelemetry import trace
from opentelemetry.trace import StatusCode

from meridian.wrappers.cost import estimate_cost


def _extract_token_counts(response: Any) -> tuple[int, int]:
    """Pull input/output token counts from a LangChain AI message."""
    usage: Any = {}
    if hasattr(response, "usage_metadata") and response.usage_metadata:
        usage = response.usage_metadata
    elif hasattr(response, "response_metadata") and response.response_metadata:
        meta = response.response_metadata
        usage = (
            meta.get("usage")
            or meta.get("token_usage")
            or meta.get("usage_metadata")
            or {}
        )

    input_tokens = int(
        usage.get("input_tokens")
        or usage.get("prompt_tokens")
        or usage.get("input_token_count")
        or usage.get("prompt_token_count")
        or 0
    )
    output_tokens = int(
        usage.get("output_tokens")
        or usage.get("completion_tokens")
        or usage.get("output_token_count")
        or usage.get("candidates_token_count")
        or 0
    )
    return input_tokens, output_tokens


def _chunk_text(content: Any) -> str:
    """Coerce an AIMessageChunk content to plain string."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            p if isinstance(p, str) else str(p.get("text", "")) if isinstance(p, dict) else ""
            for p in content
        )
    return ""


def _estimate_tokens_from_text(text: str) -> int:
    """Rough estimate: ~4 chars per token (used when model reports 0)."""
    return max(1, len(text) // 4)


def _input_text_from_args(args: tuple) -> str:
    """Extract plain text from the messages/prompt passed to astream/ainvoke."""
    msgs = args[0] if args else []
    if isinstance(msgs, str):
        return msgs
    if not hasattr(msgs, "__iter__"):
        return str(msgs)
    parts = []
    for m in msgs:
        content = getattr(m, "content", None)
        if content is None:
            content = str(m)
        parts.append(_chunk_text(content))
    return " ".join(parts)


def _wrap_invoke(original, instance, args, kwargs):
    tracer = trace.get_tracer("meridian")
    model_name = getattr(instance, "model", None) or getattr(instance, "model_name", "unknown")

    with tracer.start_as_current_span("llm.call") as span:
        span.set_attribute("llm.model", str(model_name))
        t0 = time.perf_counter()
        try:
            result = original(*args, **kwargs)
        except Exception as exc:
            span.set_status(StatusCode.ERROR, str(exc))
            span.record_exception(exc)
            raise
        finally:
            latency_ms = (time.perf_counter() - t0) * 1000
            span.set_attribute("llm.latency_ms", round(latency_ms, 2))

        in_tok, out_tok = _extract_token_counts(result)
        cost = estimate_cost(str(model_name), in_tok, out_tok)
        span.set_attribute("llm.input_tokens", in_tok)
        span.set_attribute("llm.output_tokens", out_tok)
        span.set_attribute("llm.cost_usd", cost)
        span.set_status(StatusCode.OK)
        return result


async def _wrap_ainvoke(original, instance, args, kwargs):
    tracer = trace.get_tracer("meridian")
    model_name = getattr(instance, "model", None) or getattr(instance, "model_name", "unknown")

    with tracer.start_as_current_span("llm.call") as span:
        span.set_attribute("llm.model", str(model_name))
        t0 = time.perf_counter()
        try:
            result = await original(*args, **kwargs)
        except Exception as exc:
            span.set_status(StatusCode.ERROR, str(exc))
            span.record_exception(exc)
            raise
        finally:
            latency_ms = (time.perf_counter() - t0) * 1000
            span.set_attribute("llm.latency_ms", round(latency_ms, 2))

        in_tok, out_tok = _extract_token_counts(result)
        cost = estimate_cost(str(model_name), in_tok, out_tok)
        span.set_attribute("llm.input_tokens", in_tok)
        span.set_attribute("llm.output_tokens", out_tok)
        span.set_attribute("llm.cost_usd", cost)
        span.set_status(StatusCode.OK)
        return result


def patch_chatgoogle() -> None:
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
    except ImportError:
        return

    if not getattr(ChatGoogleGenerativeAI, "_meridian_patched", False):
        wrapt.wrap_function_wrapper(ChatGoogleGenerativeAI, "invoke", _wrap_invoke)
        wrapt.wrap_function_wrapper(ChatGoogleGenerativeAI, "ainvoke", _wrap_ainvoke)

        # wrapt can't wrap async generators, so monkey-patch astream directly.
        # The last chunk from Gemini's stream carries aggregated usage_metadata.
        _orig_astream = ChatGoogleGenerativeAI.astream

        async def _patched_astream(self, *args, **kwargs):
            tracer = trace.get_tracer("meridian")
            model_name = getattr(self, "model", None) or getattr(self, "model_name", "unknown")
            span = tracer.start_span("llm.call")
            span.set_attribute("llm.model", str(model_name))
            t0 = time.perf_counter()
            last_chunk = None
            output_parts: list[str] = []
            try:
                async for chunk in _orig_astream(self, *args, **kwargs):
                    last_chunk = chunk
                    if hasattr(chunk, "content"):
                        output_parts.append(_chunk_text(chunk.content))
                    yield chunk
                if last_chunk is not None:
                    in_tok, out_tok = _extract_token_counts(last_chunk)
                    # Some streaming models (e.g. Gemini preview) report 0 tokens.
                    # Fall back to character-based estimation so cost is non-zero.
                    if in_tok == 0 and out_tok == 0:
                        out_tok = _estimate_tokens_from_text("".join(output_parts))
                        in_tok  = _estimate_tokens_from_text(_input_text_from_args(args))
                    cost = estimate_cost(str(model_name), in_tok, out_tok)
                    span.set_attribute("llm.input_tokens", in_tok)
                    span.set_attribute("llm.output_tokens", out_tok)
                    span.set_attribute("llm.cost_usd", cost)
                span.set_status(StatusCode.OK)
            except Exception as exc:
                span.set_status(StatusCode.ERROR, str(exc))
                span.record_exception(exc)
                raise
            finally:
                span.set_attribute("llm.latency_ms", round((time.perf_counter() - t0) * 1000, 2))
                span.end()

        ChatGoogleGenerativeAI.astream = _patched_astream
        ChatGoogleGenerativeAI._meridian_patched = True
