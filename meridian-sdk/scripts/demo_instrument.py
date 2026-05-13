"""Minimal demo: 2-node LangGraph with a Gemini call, prints OTel spans."""
from __future__ import annotations

import os
import sys

# Allow running from repo root without installing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from typing import TypedDict

from meridian import instrument

# ── instrument BEFORE importing LangGraph / LangChain ──────────────────────
otlp = os.getenv("OTLP_ENDPOINT")
instrument("demo", otlp_endpoint=otlp)
# ───────────────────────────────────────────────────────────────────────────

from langgraph.graph import StateGraph, END
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage


class AgentState(TypedDict):
    question: str
    answer: str


MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
llm = ChatGoogleGenerativeAI(model=MODEL)


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
