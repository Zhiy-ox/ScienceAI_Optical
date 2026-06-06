# Orchestration Migration Plan — Graph-Based Pipeline (LangGraph)

> Status: **Planned** · Branch: `claude/build-science-ai-K6osh` · Supersedes the hand-rolled `ResearchOrchestrator`

## 1. Goal & Rationale

Replace the sequential, monolithic `ResearchOrchestrator` with a **LangGraph state-graph** that models the research pipeline as nodes + conditional edges. This is a control-flow change only — **all agents, both LLM backends (API + CLI), cost tracking, prompt caching, paper search, and Zotero integration are reused unchanged**.

### What it fixes (from the current architecture)

| Current pain point | Graph solution |
|---|---|
| `phase3 → phase2 → phase1` hardcoded nesting | Flat node DAG with conditional phase-exit edges |
| 3 feedback loops embedded in orchestrator methods | Feedback loops = conditional edges (bounded cycles) |
| State mutated in-place, dict-spread between phases | Typed `ResearchState` with reducers, immutable transitions |
| Sessions in in-memory `_sessions` dict — lost on restart | Postgres checkpointer, `thread_id = session_id`, resume mid-run |
| Dashboard polls every 5s, no live progress | SSE streaming of node-by-node progress |
| Per-paper deep-read & critique run serially | Parallel fan-out via `Send` API (concurrency-capped) |
| No approval/oversight | Human-in-the-loop `interrupt()` gates |

### Locked decisions
- **Framework:** LangGraph (model-agnostic — nodes call `self.llm.complete()` as today)
- **Capabilities:** durable resume · live streaming · parallel fan-out · human-in-the-loop
- **Rollout:** incremental, behind `ORCHESTRATOR_MODE=graph|legacy` feature flag

---

## 2. Target Architecture

### 2.1 State schema — `orchestrator/graph/state.py`

```python
import operator
from typing import Annotated, Any, TypedDict

class ResearchState(TypedDict):
    # --- inputs ---
    session_id: str
    question: str
    max_papers: int
    phase: int                 # 1 | 2 | 3 — controls graph exit
    user_background: str
    source: str                # web | zotero | both
    hitl_gates: list[str]      # e.g. ["plan", "gaps"]; empty = autonomous

    # --- stage outputs (accumulating lists use reducers) ---
    plan: dict | None
    all_papers: Annotated[list[dict], operator.add]
    triage_results: Annotated[list[dict], operator.add]
    knowledge_objects: Annotated[list[dict], operator.add]   # fan-in target
    critiques: Annotated[list[dict], operator.add]           # fan-in target
    gaps: list[dict]
    verification_results: list[dict]
    verified_gaps: list[dict]
    ideas: list[dict]
    experiment_plans: list[dict]
    report: dict | None
    zotero_collection_key: str | None

    # --- loop counters (checkpointed, replace FeedbackController's dict) ---
    search_refine_count: int
    gap_retry_count: int
    idea_regen_count: int

    # --- meta ---
    status: str
    cost_records: Annotated[list[dict], operator.add]        # durable cost
    cost_summary: dict
```

### 2.2 Graph topology

```
        START
          │
          ▼
      [plan]  ──HITL gate "plan"?──▶ interrupt → /resume
          │
          ▼
     [search] ◀───────────────────────┐
          │                           │ refine: >30% new keywords
          ▼                           │ AND search_refine_count < 3
     [triage]                         │
          │                           │
          ▼                           │
   [select_papers]  (pure fn)         │
          │                           │
          ▼                           │
   [deep_read_dispatch] ─Send×N─▶ [deep_read_one] (parallel, sem-capped)
          │                           │
          ▼  fan-in via reducer       │
   [refine_decision] ─────────────────┘
          │
          ├── phase == 1 ──────────────▶ END
          ▼ (phase ≥ 2)
   [critique_dispatch] ─Send×N─▶ [critique_one] (parallel)
          │
          ▼  fan-in
      [index]                         (vector + graph stores)
          │
          ▼
    [gap_detect] ◀────────────────────┐
          │                           │ retry: <30% verified
          ▼                           │ AND gap_retry_count < 3
     [verify] ──────────────────────--┘
          │
          ├── phase == 2 ──────────────▶ END
          ▼ (phase == 3)  ──HITL gate "gaps"?──▶ interrupt → /resume
     [idea] ◀──────────────────────────┐
          │                            │ regen: feasibility < 0.4
          ▼                            │ AND idea_regen_count < 3
   [experiment] ──────────────────────┘
          │
          ▼
     [report]
          │
          ▼
   [zotero_export]
          │
          ▼
         END
```

### 2.3 Dependency injection — `Deps` in config

LangGraph passes `config` as the 2nd arg to every node. Runtime services live there, fixing the "agents instantiated inside orchestrator" coupling:

```python
@dataclass
class Deps:
    llm: LLMClient | CLILLMClient
    search: PaperSearchService
    cost_tracker: CostTracker
    feedback: FeedbackController
    vector_store: Any | None
    graph_store: Any | None
    embedding_fn: Any | None
    zotero_client: Any | None

# kickoff
config = {"configurable": {"thread_id": session_id, "deps": deps}}

# inside a node
async def plan_node(state: ResearchState, config) -> dict:
    deps: Deps = config["configurable"]["deps"]
    planner = QueryPlanner(deps.llm, session_id=state["session_id"])
    plan = await planner.run(question=state["question"])
    return {"plan": plan, "status": "planned"}
```

### 2.4 Checkpointing (durable resume)

- `AsyncPostgresSaver` from `langgraph-checkpoint-postgres` (uses **psycopg v3**, not asyncpg).
- Convert DSN: `postgresql+asyncpg://…` → `postgresql://…` for the checkpointer connection.
- `graph = builder.compile(checkpointer=saver, interrupt_before=[...])`.
- One **thread per session** (`thread_id = session_id`). State persists after every node → survives restart; resume from last completed node instead of restarting.
- `graph.aget_state(config)` → `StateSnapshot` with `.values` (results) and `.next` (pending nodes) → powers the status/results endpoints. The in-memory `_sessions` dict is retired.

### 2.5 Streaming (live progress)

- New endpoint `GET /research/{id}/stream` → SSE.
- `async for mode, chunk in graph.astream(inp, config, stream_mode=["updates","custom"]):` → yield SSE frames.
- Nodes emit human-readable status via `get_stream_writer()` (e.g. `writer({"stage":"triage","msg":"Triaging 85 papers…"})`).
- Dashboard swaps 5s polling for an `EventSource` subscription.

### 2.6 Human-in-the-loop gates

- `from langgraph.types import interrupt, Command`.
- A gate node calls `decision = interrupt({"type":"approve_plan","plan":state["plan"]})`; graph pauses and checkpoints.
- Resume: `POST /research/{id}/resume {decision, edits?}` → `graph.ainvoke(Command(resume=decision), config)`.
- Gates are opt-in per session via `hitl_gates` (`[]` = fully autonomous, preserving today's behavior).

### 2.7 Parallel fan-out

- `deep_read_dispatch` returns `[Send("deep_read_one", {"paper": p, "priority": pr}) for p, pr in selected]`.
- `deep_read_one` reads one paper; results reduce into `knowledge_objects` via the `operator.add` reducer.
- Same pattern for `critique_dispatch` → `critique_one`.
- Concurrency cap respected through a shared `asyncio.Semaphore` in `Deps` (CLI tools especially are heavy).

### 2.8 Cost durability

- Each node snapshots **newly-added** `CallRecord`s (diff the tracker before/after agent calls) and appends them to `state["cost_records"]` via the reducer → costs survive resume.
- `cost_summary` recomputed from `cost_records` at terminal/stream points.

---

## 3. Reused Unchanged

`agents/*` (all 8 + gap-detection mechanisms) · `services/llm_client.py` · `services/cli_llm_client.py` · `services/paper_search.py` · `services/zotero_client.py` · `storage/vector_store.py` · `storage/graph_store.py` · `cost/tracker.py` · `orchestrator/model_router.py` · `orchestrator/feedback.py` (threshold logic called from edge functions; counters move into state).

---

## 4. New & Modified Files

| File | Action | Purpose |
|---|---|---|
| `orchestrator/graph/state.py` | **new** | `ResearchState` TypedDict + reducers |
| `orchestrator/graph/deps.py` | **new** | `Deps` dataclass (DI container) |
| `orchestrator/graph/nodes.py` | **new** | Node fns wrapping existing agents |
| `orchestrator/graph/edges.py` | **new** | Conditional routing (loops, phase-exit, HITL) |
| `orchestrator/graph/builder.py` | **new** | `build_graph()` → compiled `StateGraph` |
| `orchestrator/graph/runner.py` | **new** | `GraphRunner`: kickoff / stream / resume / get_state |
| `config.py` | modify | `orchestrator_mode`, `hitl_gates`, checkpointer DSN, fan-out concurrency |
| `api/routes.py` | modify | Branch on mode; add `/stream` (SSE) + `/resume`; read state from checkpointer |
| `api/schemas.py` | modify | `ResumeRequest`, stream-event + HITL schemas |
| `pyproject.toml` | modify | Add `langgraph`, `langgraph-checkpoint-postgres`, `psycopg[binary]` |
| `dashboard/src/lib/api.ts` | modify | `streamSession()` (EventSource), `resumeSession()` |
| `dashboard/src/app/session/page.tsx` | modify | Live SSE progress + approval UI |
| `dashboard/src/components/PipelineProgress.tsx` | **new** | Animated node-by-node progress rail |
| `tests/test_graph/*` | **new** | Node, edge-routing, and e2e graph tests (mocked LLM) |

---

## 5. Incremental Rollout — each stage shippable & testable

**Stage 1 — Foundation (linear graph, flagged, in-memory checkpointer)** ✅ *Done*
State + Deps + nodes for the happy path (plan→search→triage→select→deep_read→critique→index→gap→verify→idea→experiment→report→zotero), wired as a straight line with phase-exit edges. `ORCHESTRATOR_MODE=graph` runs it via `MemorySaver`. Validate output parity vs. legacy on a Phase-1 run.

**Stage 2 — Feedback loops as conditional edges** ✅ *Done*
Ported the 3 loops to `add_conditional_edges` using `FeedbackController` thresholds + state counters. Each loop is a `*_decision` node (mutates transient state, increments a checkpointed counter) feeding a pure router (`after_refine_decision` / `after_gap_retry_decision` / `after_idea_regen_decision`). Processing nodes (search/triage/select/deep_read) made re-entrant so loop passes only handle new items (reducers never double-count). Bounded by `MAX_LOOP_ITERATIONS=3`; runner sets `recursion_limit=100`. Unit-tested each router + decision node (trigger + max-iteration bounds) plus an e2e refinement-loop run through `ainvoke`.

**Stage 3 — Postgres checkpointing (durable resume)** ✅ *Done*
Checkpointer factory (`checkpointer.py`) creates `AsyncPostgresSaver` if `checkpointer_dsn` is configured and Postgres is reachable, otherwise falls back to `MemorySaver` (in-memory). `GraphRunner` refactored as a shared singleton: LLM client + search + checkpointer are shared across sessions; per-session resources (cost tracker, graph store, zotero client) passed to `run()`. Status/results endpoints read from the checkpointer in graph mode (survives restart); `_sessions` kept as a lightweight in-memory registry for active runs. App lifespan hook closes the Postgres connection on shutdown.

**Stage 4 — Parallel fan-out**
Convert deep-read & critique to `Send` map-reduce with a shared semaphore. Benchmark wall-clock vs. serial on a 15-paper run.

**Stage 5 — Streaming SSE**
Add `/research/{id}/stream`; emit `get_stream_writer()` progress from nodes. Dashboard subscribes via `EventSource`; render `<PipelineProgress>`. Keep polling as fallback.

**Stage 6 — Human-in-the-loop**
Add `interrupt()` gate nodes for `plan` and `gaps`; `interrupt_before` at compile; `/resume` endpoint; dashboard approval cards (approve / edit / reject).

**Stage 7 — Parity validation & cutover**
Side-by-side legacy vs. graph on a fixed question set; compare papers/gaps/ideas/cost. Flip default `ORCHESTRATOR_MODE=graph`; mark legacy deprecated; remove after a soak period.

---

## 6. API Changes

```
GET  /research/{id}/stream     # SSE: node updates + custom progress + tokens
POST /research/{id}/resume     # body: {gate, decision: approve|reject|edit, edits?}
GET  /research/{id}/status     # now reads checkpointer state (.next = pending nodes)
GET  /research/{id}/results    # now reads checkpointer state values
```

`POST /research/start` gains optional `hitl_gates: list[str]`.

---

## 7. Dashboard Changes

- **New Research:** optional toggles "Pause to approve search plan" / "Pause to approve gaps" → `hitl_gates`.
- **Session page:** replace polling with `EventSource`; `<PipelineProgress>` shows the 13-node rail lighting up live; approval cards appear on interrupt and call `/resume`.

---

## 8. Dependencies

```toml
langgraph>=0.2
langgraph-checkpoint-postgres>=2.0
psycopg[binary]>=3.2
```

(All MIT/compatible; psycopg is for the checkpointer only — app data keeps asyncpg.)

---

## 9. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| LangGraph learning-curve / API drift | Pin versions; isolate all LangGraph use under `orchestrator/graph/`; agents stay framework-free |
| psycopg vs asyncpg dual driver | Checkpointer uses its own psycopg DSN; app DB unchanged |
| CLI backend slow under fan-out | Shared semaphore + per-node timeout already in `CLILLMClient` |
| Behavior drift from legacy | Feature flag + Stage-7 parity harness before cutover |
| Cost double-counting on resume | Cost records keyed by `call_id`; dedupe on read |

---

## 10. Acceptance Criteria

1. `ORCHESTRATOR_MODE=graph` runs Phases 1–3 end-to-end with output parity to legacy.
2. Killing the server mid-run and restarting **resumes** from the last completed node.
3. Dashboard shows **live** node-by-node progress (no polling).
4. Deep-read/critique run **concurrently** (measurable wall-clock drop).
5. With `hitl_gates=["plan","gaps"]`, the run **pauses** for approval and **resumes** on `/resume`.
6. All existing tests pass; new graph tests (nodes, edge routers, e2e) green.
7. Legacy path still runs under `ORCHESTRATOR_MODE=legacy` until cutover.
