# Tracely — LLM Observability Platform

> Real-time tracing, cost tracking, latency analysis, and alerting for LangGraph agents powered by Gemini.

![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111%2B-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)
![OpenTelemetry](https://img.shields.io/badge/OpenTelemetry-OTLP-blueviolet?logo=opentelemetry)
![License](https://img.shields.io/badge/License-MIT-green)

---

## What is Tracely?

Tracely is an end-to-end LLM observability platform. It instruments your LangGraph agent pipelines with **two lines of code**, captures every LLM call as an OpenTelemetry span, and streams it into a dashboard that shows you exactly what your agents are doing, how much it costs, and when something goes wrong.

Built for teams running **LangGraph + Gemini** in production — or anyone who wants deep visibility into multi-agent AI systems.

---

## Features

| Feature | Description |
|---|---|
| **Trace Waterfall** | Visualize the full execution tree of every agent run — nodes, LLM calls, parent/child relationships, and exact latencies |
| **Cost Breakdown** | Per-node LLM cost in µUSD, stacked bar chart across recent runs |
| **Latency Heatmap** | Spot slow nodes at a glance across your last 20 runs |
| **Prompt Diff** | Side-by-side comparison of LLM inputs between any two runs |
| **Real-time Alerts** | WebSocket-driven alert feed — fires instantly when budget, latency, or loop thresholds are breached |
| **Regression Trends** | Time-bucketed charts for avg latency, avg cost, run count, and error rate |
| **Global Service Filter** | Filter every view by service name from the sidebar |
| **Zero-code LangGraph support** | Patches `StateGraph.compile()` to auto-instrument all nodes |

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  Your LangGraph App                     │
│                                                         │
│   from tracely import instrument                        │
│   instrument("my-service")          ← 2 lines           │
│                                                         │
│   [ Searcher ] → [ Critic ] → [ Synthesizer ]           │
│        ↓               ↓              ↓                 │
│   langgraph.node   llm.call      llm.call spans         │
└───────────────────────┬─────────────────────────────────┘
                        │ OTLP HTTP (protobuf)
                        ▼
┌─────────────────────────────────────────────────────────┐
│              meridian-server  :8001                     │
│                                                         │
│  POST /v1/traces  →  parse protobuf  →  SQLite          │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌────────────────────┐    │
│  │  runs    │  │  spans   │  │  alerts             │    │
│  └──────────┘  └──────────┘  └────────────────────┘    │
│                                                         │
│  REST API: /api/runs  /api/runs/{id}/cost               │
│            /api/regression  /api/alerts                 │
│  WebSocket: /ws/alerts  (real-time push)                │
└───────────────────────┬─────────────────────────────────┘
                        │ REST + WebSocket
                        ▼
┌─────────────────────────────────────────────────────────┐
│              meridian-ui  :5173                         │
│                                                         │
│  Overview · Runs · Cost · Latency · Diff · Alerts · Trends │
└─────────────────────────────────────────────────────────┘
```

### Repository layout

```
tracely/
├── meridian-sdk/        # Python instrumentation package
│   └── meridian/
│       ├── __init__.py          # instrument() / shutdown() API
│       ├── tracer.py            # OTel TracerProvider setup
│       ├── middleware.py        # ASGI HTTP tracing middleware
│       └── wrappers/
│           ├── langgraph.py     # Patches StateGraph.compile()
│           ├── langchain_llm.py # Patches ChatGoogleGenerativeAI
│           └── cost.py          # Per-model token cost table
├── meridian-server/     # FastAPI backend
│   └── server/
│       ├── main.py              # App entry point, CORS, routers
│       ├── db.py                # Async SQLite layer
│       ├── otlp.py              # OTLP ingestion endpoint
│       ├── models.py            # Pydantic response models
│       ├── api/                 # REST route handlers
│       │   ├── runs.py
│       │   ├── spans.py
│       │   ├── cost.py
│       │   ├── alerts.py
│       │   └── regression.py
│       └── alerts/              # Alert engine
│           ├── engine.py
│           ├── rules.py
│           └── websocket.py
└── meridian-ui/         # React + Vite dashboard
    └── src/
        ├── App.tsx              # Shell, sidebar nav, global filter
        ├── api/
        │   ├── client.ts        # Typed REST client
        │   └── websocket.ts     # useAlerts() hook
        └── components/
            ├── Overview.tsx
            ├── RunList.tsx
            ├── TraceWaterfall.tsx
            ├── CostChart.tsx
            ├── LatencyHeatmap.tsx
            ├── PromptDiff.tsx
            ├── AlertFeed.tsx
            └── RegressionView.tsx
```

---

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- A Google API key with Gemini access

### 1. Clone and set up environment

```bash
git clone https://github.com/yourname/tracely.git
cd tracely
cp .env.example .env
# Add your GOOGLE_API_KEY to .env
```

### 2. Install the SDK

```bash
pip install -e meridian-sdk/
```

### 3. Start the server

```bash
make server
# or manually:
cd meridian-server
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn server.main:app --host 0.0.0.0 --port 8001 --reload
```

### 4. Start the dashboard

```bash
make ui
# or manually:
cd meridian-ui
npm install
npm run dev
```

Open **http://localhost:5173**

### 5. Run the demo

```bash
make demo
```

This runs a mock LangGraph agent (no API key needed) and populates the dashboard with sample traces.

---

## Instrumenting Your Own Project

Add **two lines** before your LangGraph imports:

```python
from meridian import instrument
instrument("my-agent-service", otlp_endpoint="http://localhost:8001/v1/traces")

# All LangGraph and Gemini imports must come AFTER instrument()
from my_project.graph import graph
```

Call `meridian.shutdown()` before process exit to flush any buffered spans.

### What gets instrumented automatically

| Span type | Attributes captured |
|---|---|
| `langgraph.node` | `node.name`, `node.latency_ms`, `node.input_state_keys`, `node.output_state_keys` |
| `llm.call` | `llm.model`, `llm.input_tokens`, `llm.output_tokens`, `llm.cost_usd`, `llm.latency_ms` |

---

## Alert Rules

Alerts fire automatically after every run and are pushed to the UI via WebSocket.

| Rule | Trigger | Severity |
|---|---|---|
| `loop_detected` | Any LangGraph node executes > 5 times in a single run | warning |
| `budget_exceeded` | Total LLM cost for a run exceeds $0.10 | error |
| `latency_spike` | Any single span takes longer than 2000 ms | warning |

Each rule fires **at most once per run** — enforced by a `UNIQUE(run_id, rule_name)` index. OTLP retries and multi-batch traces produce no duplicate alerts.

---

## Supported Models

Tracely ships with cost rates for all current Gemini models:

| Model | Input (per 1K tokens) | Output (per 1K tokens) |
|---|---|---|
| gemini-2.5-pro | $0.00125 | $0.010 |
| gemini-2.5-flash | $0.000075 | $0.0003 |
| gemini-2.0-flash | $0.000075 | $0.0003 |
| gemini-1.5-pro | $0.00125 | $0.005 |
| gemini-1.5-flash | $0.000075 | $0.0003 |

GPT-4, GPT-3, and Claude model families are also estimated via prefix fallback.

---

## API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/v1/traces` | POST | OTLP protobuf trace ingestion |
| `/api/runs` | GET | Paginated list of runs (filter by service, model, time range) |
| `/api/runs/{id}` | GET | Single run details |
| `/api/runs/{id}/spans` | GET | Full span tree for a run |
| `/api/runs/{id}/cost` | GET | Cost breakdown by node |
| `/api/alerts` | GET | Paginated alert history |
| `/api/regression` | GET | Time-bucketed trend data (day/hour) |
| `/ws/alerts` | WS | Real-time alert push stream |

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DB_PATH` | `./meridian.db` | SQLite database file path |
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `8001` | Server listen port |
| `GOOGLE_API_KEY` | — | Required for live Gemini calls |

---

## Tech Stack

**Backend:** Python 3.11 · FastAPI · aiosqlite · OpenTelemetry SDK · Protobuf

**Frontend:** React 18 · TypeScript · Vite · Tailwind CSS · Recharts

**Instrumentation:** OpenTelemetry · wrapt · langchain-google-genai · langgraph

---

## Running Tests

```bash
make test
# or:
cd meridian-sdk && python -m pytest tests/
```

---
