# Tracely — Internal Build Notes

> Everything we built, every decision we made, every bug we hit, and how we got out.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [System Architecture & Design Decisions](#2-system-architecture--design-decisions)
3. [Phase-by-Phase Build Log](#3-phase-by-phase-build-log)
4. [Bugs, Blockers & Debugging Sessions](#4-bugs-blockers--debugging-sessions)
5. [SDK Deep Dive](#5-sdk-deep-dive)
6. [Server Deep Dive](#6-server-deep-dive)
7. [Frontend Deep Dive](#7-frontend-deep-dive)
8. [Performance & Scalability Notes](#8-performance--scalability-notes)
9. [Known Limitations](#9-known-limitations)

---

## 1. Project Overview

**What it is:** A full-stack LLM observability platform that instruments LangGraph multi-agent applications running on Gemini, collects OpenTelemetry traces, stores them in SQLite, and visualizes them in a React dashboard.

**Why we built it:** LangGraph agents are complex pipelines with multiple nodes, each potentially calling one or more LLMs. Without observability you can't answer: Which node is slow? Which LLM call is expensive? Did the agent loop? Did a run cost more than expected? Tracely answers all of these.

**Target stack:** Python LangGraph + `langchain-google-genai` (Gemini) + FastAPI backends. The UI is model-agnostic but cost estimation is Gemini-focused.

---

## 2. System Architecture & Design Decisions

### 2.1 Three-tier layout

```
SDK (Python) → Server (FastAPI + SQLite) → UI (React + Vite)
```

Each tier is a separate directory (`meridian-sdk/`, `meridian-server/`, `meridian-ui/`) with its own dependency management. This was intentional — the SDK is distributed separately (users `pip install` it into their own app), while the server and UI are operator-deployed.

### 2.2 Why OpenTelemetry?

We chose OTLP (OpenTelemetry Protocol) over a custom format for several reasons:

- **Standard wire format**: Any OTel-compatible agent can send traces without SDK modification
- **Span hierarchy built-in**: Parent/child relationship via `trace_id` + `parent_span_id` — we get the whole tree for free
- **Batching & retry**: The OTel SDK's `BatchSpanProcessor` handles buffering, retry, and backpressure so we don't have to
- **Future-proof**: Could later swap the collector backend (Jaeger, Tempo, etc.) without changing the SDK

The OTLP export format is protobuf over HTTP (not gRPC) because it's simpler to implement the receiver side in FastAPI with just the `opentelemetry-proto` package.

### 2.3 Why SQLite?

Alternatives considered: PostgreSQL, DuckDB, in-memory.

We chose SQLite because:
- **Zero operational overhead**: No separate process, no connection pooling to configure, file-based
- **Async via aiosqlite**: The `aiosqlite` library wraps SQLite in a thread pool, giving us non-blocking I/O compatible with FastAPI's async model
- **WAL mode**: We enable `PRAGMA journal_mode=WAL` on every connection so concurrent readers don't block the writer — important because the UI is constantly querying while OTLP data is being written
- **Foreign keys**: Enabled via `PRAGMA foreign_keys=ON` to maintain referential integrity between runs → spans → alerts

The schema is intentionally flat — three tables (runs, spans, alerts) with a JSON blob for span attributes. This keeps the schema stable even as we add new OTel attributes without migrations.

### 2.4 Span attribute storage as JSON

Span attributes are heterogeneous — `llm.cost_usd` (float), `llm.model` (string), `node.input_state_keys` (list). Rather than creating a separate `attributes` table or columns for every possible key, we store the full attributes dict as a JSON string in a single `TEXT` column.

SQLite's `json_extract()` function lets us query into this blob efficiently:
```sql
SELECT json_extract(attributes, '$.llm.cost_usd') FROM spans WHERE name = 'llm.call'
```

This is used in `recompute_run_totals()` to sum costs across all stored spans for a run.

### 2.5 Why monkey-patching over subclassing?

The SDK patches existing LangChain/LangGraph classes at the call site rather than requiring users to subclass or use a special wrapper. The reasoning:

- **No user code changes**: Users import their LangGraph graph as normal; instrumentation happens transparently
- **Works with any constructor**: `ChatGoogleGenerativeAI(model="gemini-2.5-flash")` — no wrapping needed
- **LangGraph nodes**: LangGraph doesn't expose a clean hook for node execution. We patch `StateGraph.compile()` and then wrap the inner `RunnableCallable` of each node. This intercepts execution without requiring users to annotate their node functions

`wrapt` is used for `invoke` and `ainvoke` because it correctly preserves function signatures, docstrings, and `__wrapped__` references. For `astream` we can't use `wrapt` (it doesn't support async generators), so we monkey-patch the class attribute directly.

### 2.6 Real-time alerts via WebSocket

Alerts are evaluated synchronously at the end of every OTLP batch (in `otlp.py`). After evaluation, fired alerts are:
1. Persisted to the `alerts` table
2. Broadcast to all connected WebSocket clients via `ConnectionManager`

The `AlertFeed.tsx` component connects to `/ws/alerts` on mount. New alerts arrive without polling, which means the UI updates within milliseconds of a run completing.

### 2.7 Frontend architecture

The UI is a single-page app with a sidebar for navigation and a main content area. Key decisions:

- **No state management library**: The app state (selected view, selected run, global service filter) is simple enough to live in `App.tsx` with `useState`. No Redux/Zustand needed.
- **Split layout for Runs view**: The Runs view has a two-pane layout (run list + trace waterfall). All other views are full-width. This was motivated by UX — the waterfall needs horizontal space.
- **Global service filter in sidebar**: Rather than each component having its own service dropdown, a single `globalService` state in `App.tsx` propagates down to all views. This gives consistent filtering across every tab.
- **Recharts for charts**: Recharts is a well-maintained React charting library with built-in support for responsive containers, stacked bars, and line charts. Chosen over Chart.js (less React-native), Victory (heavier), and D3 (too low-level for the time budget).

---

## 3. Phase-by-Phase Build Log

### Phase 1 — SDK Foundation

Built the core instrumentation package:
- `tracer.py`: Sets up an OTel `TracerProvider` with a `BatchSpanProcessor` pointing at the OTLP endpoint
- `wrappers/langgraph.py`: Patches `StateGraph.compile()` by iterating over `graph.nodes` and replacing each node's `bound` callable with a wrapper that creates a `langgraph.node` span
- `wrappers/langchain_llm.py`: Patches `ChatGoogleGenerativeAI.invoke` and `ainvoke` using `wrapt` to create `llm.call` spans with model, token, cost, and latency attributes
- `wrappers/cost.py`: Static lookup table mapping model names to per-1K-token input/output rates

**Key insight from Phase 1**: The `instrument()` function must be called before any LangGraph imports because Python evaluates `StateGraph.compile()` at import time in many patterns. We document this ordering requirement explicitly.

### Phase 2 — Server

Built the FastAPI backend:
- `otlp.py`: Receives protobuf-encoded OTLP spans, decodes with `opentelemetry-proto`, groups by trace_id, upserts runs, bulk-inserts spans
- `db.py`: Async SQLite layer with schema init, CRUD functions
- `api/runs.py`, `api/spans.py`, `api/cost.py`, `api/alerts.py`: REST endpoints
- `alerts/rules.py` + `alerts/engine.py`: Three alert rules evaluated after each trace batch
- `alerts/websocket.py`: WebSocket manager for real-time alert broadcast

### Phase 3 — UI Foundation

Built the React dashboard with:
- `RunList.tsx`: Paginated list of runs with service/model filters
- `TraceWaterfall.tsx`: Span tree rendered as a horizontal waterfall using CSS positioning
- `CostChart.tsx`: Recharts stacked bar chart of LLM cost per node per run
- `LatencyHeatmap.tsx`: Grid heatmap of node latency across runs
- `PromptDiff.tsx`: Side-by-side diff of LLM messages between two runs
- `AlertFeed.tsx`: WebSocket-connected alert list with live indicator

### Phase 4 — Live Agent Integration

Integrated with `live_research_intel` (a real LangGraph research agent with Searcher/Critic/Synthesizer nodes) and `codejudge` (a code evaluation agent).

This phase surfaced the most bugs — see Section 4.

### Phase 5 — Regression & Overview

- `api/regression.py`: Time-bucketed trend endpoint using SQLite `strftime()` for day/hour grouping
- `RegressionView.tsx`: Dual-panel line charts (latency+cost, run count+error rate)
- `Overview.tsx`: KPI cards + recent runs table as the default landing view

### Phase 6 — UI Redesign

Replaced the original tab-bar layout (which duplicated navigation in both a top bar and a sidebar) with a clean sidebar-only design:
- Single `NAV` array drives both the sidebar buttons and the view renderer
- Inline SVG icons (no icon library dependency)
- Split layout only for Runs view; all other views get full-width treatment
- Global service filter dropdown anchored to sidebar footer

---

## 4. Bugs, Blockers & Debugging Sessions

### Bug 1: `astream` not instrumented → no `llm.call` spans for streaming agents

**Symptom**: `live_research_intel` agent ran successfully but no `llm.call` spans appeared in the UI. Only `langgraph.node` spans were visible.

**Root cause investigation**:
1. Checked `live_research_intel/backend/agents/_common.py` — confirmed it uses `stream_llm_with_retry()` which calls `get_llm().astream(messages)` (not `invoke` or `ainvoke`)
2. Our wrapper only patched `invoke` and `ainvoke`. `astream` was untouched.
3. Tried `wrapt.wrap_function_wrapper(ChatGoogleGenerativeAI, "astream", wrapper_fn)` — this silently fails because `wrapt` can't wrap async generator methods. The original `astream` is an `async def` that uses `yield`, making it an async generator function, not a coroutine. `wrapt` wraps it as a regular function, breaking the iteration protocol.

**Fix**: Monkey-patch the class attribute directly:
```python
_orig_astream = ChatGoogleGenerativeAI.astream

async def _patched_astream(self, *args, **kwargs):
    # ... span setup ...
    async for chunk in _orig_astream(self, *args, **kwargs):
        # ... accumulate output ...
        yield chunk
    # ... finalize span ...

ChatGoogleGenerativeAI.astream = _patched_astream
```

The wrapper is itself an async generator, so the iteration protocol is preserved end-to-end.

---

### Bug 2: Gemini streaming returns zero tokens → cost always $0

**Symptom**: After fixing Bug 1, `llm.call` spans appeared but `llm.cost_usd` was `0.0`. `llm.input_tokens` and `llm.output_tokens` were also `0`.

**Root cause investigation**:
1. Wrote a test script that called `ChatGoogleGenerativeAI(model="gemini-3.1-flash-lite-preview").astream(messages)` directly and printed the `usage_metadata` on the last chunk
2. Result: `{'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0}` — the model genuinely returns zero in streaming mode
3. Deeper investigation: `langchain-google-genai` v2.0.10 uses the deprecated `google.generativeai` backend. The `generateContent` streaming response from that backend doesn't include `usageMetadata` in the final chunk for this particular preview model variant.

**Fix**: Character-based token estimation as fallback:
```python
if in_tok == 0 and out_tok == 0:
    out_tok = _estimate_tokens_from_text("".join(output_parts))
    in_tok  = _estimate_tokens_from_text(_input_text_from_args(args))
```

~4 characters per token is a rough industry estimate (GPT/Gemini tokenizers average around 3.5–4.5 chars/token for English). Not exact but better than zero.

---

### Bug 3: Model `gemini-3.1-flash-lite-preview` not in cost table → `estimate_cost()` returns 0.0

**Symptom**: Even after fixing the token count (Bug 2), cost was still 0. Tokens were non-zero now.

**Root cause**: The cost table in `wrappers/cost.py` had `gemini-3.1-flash-lite` but not `gemini-3.1-flash-lite-preview`. The `-preview` suffix made the lookup fail.

**Fix**: Two-layer defense:
1. Added `gemini-3.1-flash-lite-preview` explicitly to the table
2. Added suffix stripping logic: strip `-preview`, `-exp`, `-latest` from the key before lookup
3. Added prefix-based fallback: if exact match fails, try `key.startswith("gemini-3.1-flash")`, then `"gemini-2.5-flash"`, etc.

```python
bare = key.replace("-preview","").replace("-exp","").replace("-latest","").rstrip("-")
rates = COST_PER_1K_TOKENS.get(key) or COST_PER_1K_TOKENS.get(bare)
if rates is None:
    for prefix, fallback_rates in _FALLBACK_PREFIXES:
        if key.startswith(prefix) or bare.startswith(prefix):
            rates = fallback_rates
            break
```

This means any future Gemini model with an unrecognized name will still get a reasonable cost estimate rather than silently returning 0.

---

### Bug 4: OTLP batch ordering overwrites run cost with 0

**Symptom**: A run would appear in the UI with the correct token count (e.g. 2252 tokens) but `total_cost_usd = 0.0`. Refreshing didn't fix it.

**Root cause investigation**:
1. Inspected the SQLite database directly: `SELECT * FROM runs ORDER BY start_time DESC LIMIT 5` — confirmed `total_cost_usd = 0.0` despite `total_tokens > 0`
2. Traced through `otlp.py`: `upsert_run()` is called with the spans in the current OTLP batch, not all spans ever received for that trace
3. LangGraph sends spans in multiple batches. The `llm.call` span (which carries `llm.cost_usd`) arrives in the first batch. The `langgraph.node` parent span arrives in a second batch — after the node finishes. This second `upsert_run()` call sees only the parent node span (no `llm.cost_usd`), so it writes `total_cost_usd = 0.0`, overwriting the correct value from the first batch.

**Fix**: Added `recompute_run_totals()` in `db.py` that queries ALL stored spans for a run from the database after each batch and recomputes totals using `json_extract`:

```sql
SELECT
    COALESCE(SUM(CAST(json_extract(attributes,'$.llm.cost_usd') AS REAL)), 0) AS total_cost,
    COALESCE(SUM(
        COALESCE(CAST(json_extract(attributes,'$.llm.input_tokens') AS INT), 0) +
        COALESCE(CAST(json_extract(attributes,'$.llm.output_tokens') AS INT), 0)
    ), 0) AS total_tokens,
    MAX(json_extract(attributes,'$.llm.model')) AS model
FROM spans
WHERE run_id = ? AND name = 'llm.call'
```

This is called in `otlp.py` after `insert_spans_bulk()`:
```python
for trace_id in by_trace:
    await db.recompute_run_totals(trace_id)
```

The key insight: always derive run totals from the complete set of persisted spans, not from the current batch. This makes the function idempotent — calling it multiple times converges to the correct value.

---

### Bug 5: CostChart bars invisible (visible only on hover)

**Symptom**: The cost chart rendered with empty-looking bars. Hovering over each bar position showed the correct tooltip value — the bars were there but had no fill color.

**Root cause**: The original chart code used Recharts `<Cell>` components inside `<Bar>` to individually color each bar:
```tsx
<Bar dataKey={n} stackId="cost" fill={COLORS[i % COLORS.length]}>
  {rows.map((_, j) => <Cell key={j} />)}
</Bar>
```
An empty `<Cell>` with no explicit `fill` prop overrides the parent `<Bar fill>` with `undefined`, which Recharts renders as transparent.

**Fix**: Remove all `<Cell>` children — the `fill` on `<Bar>` is sufficient for uniform bar coloring:
```tsx
<Bar key={n} dataKey={n} stackId="cost" fill={COLORS[i % COLORS.length]} isAnimationActive={false} />
```

Also added `isAnimationActive={false}` to prevent the bars from flashing white during mount animation (a separate visual artifact).

---

### Bug 6: CostChart only showed mock demo data, not live agent data

**Symptom**: The cost chart populated correctly with demo runs but stayed empty after running the live agent.

**Root cause**: `CostChart` was receiving `allRuns` as a prop from `App.tsx`. `allRuns` was only populated when the user clicked the Runs view. The chart depended on state that was never fetched until a different view was visited first.

**Fix**: Removed the `runs` prop from `CostChart` entirely. The component now fetches its own data independently via `api.runs.list()` on mount. This makes it self-contained — it doesn't care what `App.tsx` has loaded.

---

### Bug 7: Recharts tooltip cursor renders white on hover

**Symptom**: Hovering over bars showed a bright white rectangle behind the tooltip, jarring against the dark theme.

**Root cause**: Recharts' default `cursor` prop for `<Tooltip>` is a filled rectangle with a light gray/white color designed for light themes.

**Fix**: Override with a near-transparent fill:
```tsx
<Tooltip cursor={{ fill: "rgba(255,255,255,0.04)" }} ... />
```

---

### Bug 8: CORS 400 on live_research_intel research queries

**Symptom**: Submitting a research question in `live_research_intel` returned a network error. The browser console showed a CORS preflight rejection from `http://localhost:8000`.

**Root cause**: `live_research_intel` frontend started on port 5174 (port 5173 was already taken by the Tracely UI). The FastAPI CORS whitelist in `live_research_intel/backend/main.py` only listed `http://localhost:5173`.

**Fix**: Added port 5174 to `allow_origins`:
```python
allow_origins=["http://localhost:5173", "http://localhost:5174"]
```

---

### Bug 9: Port 8000 not releasing after killing backend process

**Symptom**: After stopping `live_research_intel`'s backend, trying to restart it gave `Address already in use`. Killing the process PID shown in the terminal didn't free the port.

**Root cause**: `uvicorn` spawns a child process. Killing the parent (PID 24260) left the child (PID 24580) running and holding the port.

**Diagnosis**: `netstat -ano | findstr :8000` revealed PID 24580 still bound to the port.

**Fix**: Explicitly kill the child process: `taskkill /PID 24580 /F`

---

### Bug 10: Tooltip clipped by overflow scroll in Runs view

**Symptom**: Hovering over a span bar in the waterfall showed the tooltip box, but it was cut off by the scrollable detail panel. The box appeared to be "inside" the scroll container.

**Root cause**: The tooltip was `position: absolute` inside a `<div className="relative overflow-x-auto">` container. The parent panel had `overflow-y-auto`, which establishes a new stacking context that clips absolutely-positioned children.

**Fix**: Changed tooltip to `position: fixed` with mouse coordinates tracked via `onMouseEnter`/`onMouseMove`:
```tsx
// State now carries coordinates
const [tooltip, setTooltip] = useState<{ span: FlatSpan; x: number; y: number } | null>(null);

// Bar hover handlers
onMouseEnter={(e) => setTooltip({ span: s, x: e.clientX, y: e.clientY })}
onMouseMove={(e) => setTooltip((t) => t ? { ...t, x: e.clientX, y: e.clientY } : null)}

// Tooltip rendered with fixed position
<div className="fixed z-50 ..." style={{ left: tooltip.x + 14, top: tooltip.y + 14 }}>
```

Added `pointer-events-none` on the tooltip element to prevent it from stealing mouse events as the cursor moves across bars.

---

### Bug 11: Global service filter didn't propagate to Overview and RegressionView

**Symptom**: Changing the sidebar service filter had no effect on the Overview KPI cards, recent runs list, or Regression charts.

**Root cause**: `Overview` fetched its own data with no service filter. `RegressionView` had its own internal service dropdown but no connection to the global sidebar state.

**Fix**:
- Added `serviceFilter?: string` prop to both components
- `Overview` passes `service_name: serviceFilter || undefined` to `api.runs.list()` and re-fetches when `serviceFilter` changes
- `RegressionView` initializes its local `service` state from the prop and has a `useEffect` that syncs when the prop changes
- `App.tsx` passes `serviceFilter={globalService}` to both

---

### Bug 12: OTLP retry fires duplicate alerts

**Symptom**: The OTel SDK retries failed OTLP exports automatically. If the server accepted the first delivery but the SDK didn't receive the acknowledgement (network timeout), it re-sends the same batch. The alert engine re-evaluated the run and inserted a second (identical) alert row, broadcasting a duplicate notification to the UI.

**Root cause**: `insert_spans_bulk` already used `INSERT OR IGNORE` so re-delivered spans were safely deduped at the DB level. But `evaluate_run()` was called unconditionally after every batch — it has no way to know whether any spans were actually new. It re-reads all spans for the run, re-runs every rule, and calls `db.insert_alert()` which at the time used a plain `INSERT` with no uniqueness guard.

**Fix — three-layer change:**

1. **Schema** — added a unique index so the DB itself enforces one alert per rule per run:
```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_alerts_run_rule ON alerts(run_id, rule_name);
```
Migration-safe: `IF NOT EXISTS` means it applies to both new and existing databases without touching existing rows.

2. **`db.insert_alert()`** — changed to `INSERT OR IGNORE` and returns a boolean:
```python
async def insert_alert(alert: dict) -> bool:
    cur = await db.execute("INSERT OR IGNORE INTO alerts ...")
    await db.commit()
    return cur.rowcount > 0   # False = duplicate, silently skipped
```

3. **`engine.py`** — WebSocket broadcast is now gated on the return value:
```python
inserted = await db.insert_alert(alert)
if inserted:
    await manager.broadcast(alert)
```

**Result**: Retried OTLP batches produce no duplicate DB rows and no duplicate UI notifications. The fix is idempotent — calling `evaluate_run` any number of times for the same run converges to exactly one alert per rule.

**Design note**: The unique key is `(run_id, rule_name)`, meaning each rule fires at most once per run. This is intentional — you want "this run exceeded budget", not repeated pings as more spans arrive.

---

## 5. SDK Deep Dive

### 5.1 Initialization order matters

```python
from meridian import instrument
instrument("service")   # MUST be first

from my_graph import graph   # LangGraph import comes after
```

`instrument()` calls `patch_langgraph()` and `patch_chatgoogle()`. These functions monkey-patch the classes. If a class is imported before patching, the already-imported reference points to the original unpatched method. We warn about this in docs.

### 5.2 LangGraph node patching mechanics

`patch_langgraph()` wraps `StateGraph.compile()`:

```python
original_compile = StateGraph.compile

def patched_compile(self, *args, **kwargs):
    graph = original_compile(self, *args, **kwargs)
    for name, node in graph.nodes.items():
        if hasattr(node, 'bound') and callable(node.bound):
            node.bound = _make_sync_wrapper(name, node.bound)
            # async version also wrapped
    return graph
```

This runs at compile time (typically once at startup), wrapping each node's callable. At runtime, every node execution goes through the wrapper, which:
1. Opens a `langgraph.node` span
2. Records `node.name`, `node.input_state_keys`, `node.output_state_keys`
3. Marks the span as child of the current trace context (so it nests under the parent run)

### 5.3 Token extraction field names

Different LangChain/LangGraph versions and different Gemini model families return token counts under different field names. We check all known variants:

```python
input_tokens = (
    usage.get("input_tokens")          # OpenAI convention
    or usage.get("prompt_tokens")      # older OpenAI
    or usage.get("input_token_count")  # some Gemini variants
    or usage.get("prompt_token_count") # deprecated Gemini backend
    or 0
)
output_tokens = (
    usage.get("output_tokens")
    or usage.get("completion_tokens")
    or usage.get("output_token_count")
    or usage.get("candidates_token_count")  # Gemini generateContent API
    or 0
)
```

### 5.4 Streaming token estimation fallback

When `in_tok == 0 and out_tok == 0` (confirmed to happen with `gemini-3.1-flash-lite-preview` in streaming mode), we fall back to:

```python
out_tok = max(1, len("".join(output_parts)) // 4)
in_tok  = max(1, len(input_text) // 4)
```

The `max(1, ...)` ensures we never report 0 tokens even for a single-character response, which would make cost look missing rather than tiny.

---

## 6. Server Deep Dive

### 6.1 OTLP ingestion pipeline

```
POST /v1/traces (protobuf body)
  → ParseFromString(body)
  → iterate resource_spans → scope_spans → spans
  → group by trace_id into by_trace dict
  → upsert_run() for each trace_id   (creates/updates run row)
  → insert_spans_bulk()              (inserts all spans)
  → recompute_run_totals()           (re-derives cost/tokens from ALL db spans)
  → evaluate_run()                   (checks alert rules)
  → return 200
```

The `INSERT OR IGNORE` on spans means re-delivered spans (OTel retry on network failure) are safely deduped by span ID.

### 6.2 recompute_run_totals() — the idempotent aggregator

This function exists solely to fix the batch-ordering bug (Bug 4). The key property: it reads from the `spans` table (the source of truth), not from the incoming batch. This means:

- First batch arrives (has `llm.call` spans) → totals computed correctly
- Second batch arrives (has only `langgraph.node` spans) → `recompute_run_totals` re-reads all spans including the first batch → totals still correct

The `MAX(json_extract(..., '$.llm.model'))` picks up the model name from any `llm.call` span, using `COALESCE(?, model)` in the UPDATE to avoid overwriting an existing model with NULL.

### 6.3 Span tree reconstruction

`GET /api/runs/{run_id}/spans` returns a tree, not a flat list. The tree is built in `api/spans.py` using a two-pass algorithm:
1. Load all spans as dicts
2. Build an `id → span` map
3. For each span with a `parent_id`, append it to `parent.children`
4. Return only root spans (those with no parent)

The frontend (`TraceWaterfall.tsx`) then flattens this tree depth-first to render rows, carrying the depth for indentation.

### 6.4 Cost breakdown endpoint

`GET /api/runs/{run_id}/cost` returns:
```json
{
  "total_cost_usd": 0.000012,
  "breakdown": [
    { "node_name": "Searcher", "cost_usd": 0.000008, "input_tokens": 450, "output_tokens": 120 },
    { "node_name": "Synthesizer", "cost_usd": 0.000004, "input_tokens": 200, "output_tokens": 80 }
  ]
}
```

This is computed by joining `llm.call` spans with their parent `langgraph.node` span via `parent_id`. The node name comes from the parent span's `node.name` attribute. Orphan `llm.call` spans (no langgraph parent) are grouped under `"(root)"`.

### 6.5 Alert engine flow

```python
async def evaluate_run(run_id: str, spans: list[dict]) -> None:
    for rule_fn in [loop_rule, budget_rule, latency_spike_rule]:
        result = rule_fn(spans)
        if result:
            alert = {**result, "run_id": run_id, "fired_at": time.time(), "id": str(uuid4())}
            inserted = await db.insert_alert(alert)   # INSERT OR IGNORE; returns False on dedup
            if inserted:
                await manager.broadcast(alert)        # WebSocket push only on first fire
```

Rules are pure functions: `list[dict] → dict | None`. This makes them trivially testable — no DB, no async, just pass in a list of span dicts.

`insert_alert` uses `INSERT OR IGNORE` backed by `UNIQUE(run_id, rule_name)` — so even if `evaluate_run` is called multiple times for the same run (OTLP retry, legitimate second batch), each rule fires at most once per run at the database level. See Bug 12 for full context.

### 6.6 Regression query

The regression endpoint uses SQLite's `strftime` to bucket runs:

```sql
SELECT
    strftime('%Y-%m-%d', datetime(start_time, 'unixepoch')) AS bucket,
    service_name,
    COUNT(*) AS run_count,
    AVG((end_time - start_time) * 1000) AS avg_latency_ms,
    AVG(total_cost_usd) AS avg_cost_usd,
    SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS error_rate
FROM runs
GROUP BY bucket, service_name
ORDER BY bucket DESC
```

The `* 1.0` in error rate forces float division (SQLite integer division would give 0 or 1 only).

---

## 7. Frontend Deep Dive

### 7.1 App-level state model

```
App.tsx
  ├── view: View                     ← which sidebar tab is active
  ├── selected: Run | null           ← run selected in the Runs view
  ├── allRuns: Run[]                 ← top-20 runs for heatmap/diff
  ├── globalService: string          ← sidebar service filter
  └── services: string[]             ← unique service names for dropdown
```

`globalService` is the single source of truth for filtering. All components either receive it as a prop or fetch with it. This avoids per-component filter state getting out of sync.

### 7.2 Trace Waterfall rendering

Each span row has three parts:
1. **Label** (160px fixed width, indented by `depth * 12px`)
2. **Bar track** (`flex-1` width, relative positioning)
3. **Latency** (64px fixed width)

The bar position is computed as percentages of the total run time:
```tsx
const left  = ((s.start_time - tMin) / range) * 100
const width = Math.max(((s.end_time - s.start_time) / range) * 100, 0.5)
```

`Math.max(..., 0.5)` ensures even sub-millisecond spans have a visible bar (minimum 0.5% width).

### 7.3 Tooltip positioning (fixed vs absolute)

The tooltip is `position: fixed` in viewport coordinates, not `absolute` in document coordinates. This is necessary because the waterfall container has `overflow-x-auto` (for horizontal scrolling of long span names) and its parent has `overflow-y-auto`. Both establish overflow contexts that clip absolutely-positioned children.

Fixed positioning escapes all overflow contexts. The coordinates are captured from the DOM mouse event (`e.clientX`, `e.clientY`) which are already in viewport space.

`pointer-events-none` is essential — without it, the tooltip element captures mouse events as the cursor passes over it, causing the tooltip to flicker or get stuck.

### 7.4 Service filter propagation pattern

```
App.tsx (globalService state)
  ├── RunList          ← serviceFilter prop → syncs via useEffect, resets page
  ├── CostChart        ← serviceFilter prop → passes to api.runs.list
  ├── Overview         ← serviceFilter prop → passes to api.runs.list
  ├── RegressionView   ← serviceFilter prop → syncs local service state via useEffect
  ├── LatencyHeatmap   ← receives allRuns (already filtered by App.tsx)
  └── PromptDiff       ← receives allRuns (already filtered by App.tsx)
```

Two patterns:
- **Fetch-own-data components** (`RunList`, `CostChart`, `Overview`, `RegressionView`): receive `serviceFilter` prop, include it in their own `api.*` calls
- **Receive-data components** (`LatencyHeatmap`, `PromptDiff`): receive pre-filtered `allRuns` from App.tsx

The `allRuns` in App.tsx refetches whenever `globalService` changes:
```tsx
useEffect(() => {
  api.runs.list({ limit: 20, service_name: globalService || undefined })
    .then((d) => setAllRuns(d.items))
}, [globalService]);
```

### 7.5 Recharts gotchas learned

1. **Empty `<Cell>` overrides parent `<Bar fill>`**: Any `<Cell>` child inside a `<Bar>` overrides the fill with its own (potentially undefined) value. To use a uniform fill, put it on `<Bar>` only — no `<Cell>` children.

2. **Default tooltip cursor**: The default `cursor` prop renders a white/light rectangle visible on dark backgrounds. Always override: `cursor={{ fill: "rgba(255,255,255,0.04)" }}`

3. **`isAnimationActive={false}`**: The mount animation on `<Bar>` briefly shows bars as white before fading to the fill color, creating a flash. Disabling animation removes this.

4. **Dual Y-axis in `RegressionView`**: Two `<YAxis>` components need different `yAxisId` values, and each `<Line>` must reference its axis: `yAxisId="lat"` / `yAxisId="cost"`. Getting this wrong silently misscales the data.

---

## 8. Performance & Scalability Notes

### Current constraints

- **SQLite single-writer**: Only one write can happen at a time. For high-throughput agents (many concurrent runs), OTLP ingestion could queue up. WAL mode mitigates read/write contention but the write lock is still exclusive.
- **No span indexing by time**: Queries that filter by `start_time` use the `idx_runs_start` index on the runs table but span-level time queries are unindexed. For large span volumes this could slow waterfall loading.
- **No span pruning**: Spans accumulate indefinitely. No TTL or archival policy. For long-running systems, the DB will grow unbounded.

### What would need to change at scale

- Replace SQLite with PostgreSQL (concurrent writes, better JSON operators via `jsonb`)
- Add a `spans_start_time` index
- Add a background job to archive/delete runs older than N days
- Consider ClickHouse for the regression/analytics queries (columnar storage is much faster for aggregations over large span volumes)

---

## 9. Known Limitations

| Limitation | Detail |
|---|---|
| **Gemini-only cost table** | GPT/Claude rates are rough prefix fallbacks, not exact pricing |
| **Streaming token estimation** | Some Gemini preview models report 0 tokens in streaming — we estimate but it's not exact |
| **No multi-user support** | No auth, no tenancy. All runs are visible to anyone with access to the UI |
| **No span search** | Can't search for a specific prompt string or error message across all runs |
| **Single-region** | SQLite is local-only; no built-in replication or HA |
| **LangChain only** | The SDK currently only patches `langchain-google-genai`. Other LLM clients (OpenAI, Anthropic) are not auto-instrumented |
