"""Demo using a mocked Gemini response — runs without a GOOGLE_API_KEY.
   Produces the same OTel span output as the real demo.
"""
from __future__ import annotations

import os
import sys
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ── Fake langchain_google_genai so no API key needed ───────────────────────
class _FakeAIMessage:
    def __init__(self, content: str):
        self.content = content
        self.usage_metadata = {"input_tokens": 120, "output_tokens": 45}

class ChatGoogleGenerativeAI:
    _meridian_patched = False

    def __init__(self, model: str = "gemini-2.0-flash", **_):
        self.model = model

    def invoke(self, messages, **_):
        return _FakeAIMessage("OpenTelemetry is a vendor-neutral observability framework.")

    async def ainvoke(self, messages, **_):
        return _FakeAIMessage("OpenTelemetry is a vendor-neutral observability framework.")

# Inject the fake module BEFORE meridian imports it
_mod = types.ModuleType("langchain_google_genai")
_mod.ChatGoogleGenerativeAI = ChatGoogleGenerativeAI
sys.modules["langchain_google_genai"] = _mod
# ───────────────────────────────────────────────────────────────────────────

from meridian import instrument
otlp = os.getenv("OTLP_ENDPOINT")
instrument("demo", otlp_endpoint=otlp)  # OTLP if set, else console

from typing import TypedDict
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage

class AgentState(TypedDict):
    question: str
    answer: str

llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash")


def researcher(state: AgentState) -> AgentState:
    print(f"[researcher] question={state['question']!r}")
    response = llm.invoke([HumanMessage(content=f"Answer briefly: {state['question']}")])
    return {"question": state["question"], "answer": response.content}


def summariser(state: AgentState) -> AgentState:
    print(f"[summariser] answer length={len(state['answer'])}")
    response = llm.invoke(
        [HumanMessage(content=f"Summarise in one sentence: {state['answer']}")]
    )
    return {"question": state["question"], "answer": response.content}


def build_graph():
    g = StateGraph(AgentState)
    g.add_node("researcher", researcher)
    g.add_node("summariser", summariser)
    g.set_entry_point("researcher")
    g.add_edge("researcher", "summariser")
    g.add_edge("summariser", END)
    return g.compile()


if __name__ == "__main__":
    from meridian import shutdown
    graph = build_graph()
    result = graph.invoke({"question": "What is OpenTelemetry?", "answer": ""})
    print("\n=== Final answer ===")
    print(result["answer"])
    print("\n(Spans printed / exported above)")
    shutdown()  # flush BatchSpanProcessor before exit
