# ScienceAI Implementation Plan

## Overview

Build a multi-agent AI-driven scientific research assistant system per the v2 architecture.
Focus on **Phase 1 (MVP)** first — get core pipeline working end-to-end, then layer on depth.

---

## Project Structure

```
ScienceAI_Optical/
├── pyproject.toml                  # Project config, dependencies
├── .env.example                    # API keys template
├── docker-compose.yml              # PostgreSQL, Redis, (later Qdrant, Neo4j)
├── alembic/                        # DB migrations
│   └── versions/
├── src/
│   └── science_ai/
│       ├── __init__.py
│       ├── main.py                 # FastAPI app entry
│       ├── config.py               # Settings (API keys, model configs)
│       ├── api/
│       │   ├── __init__.py
│       │   ├── routes.py           # REST endpoints
│       │   └── schemas.py          # Pydantic request/response models
│       ├── orchestrator/
│       │   ├── __init__.py
│       │   ├── orchestrator.py     # Main pipeline controller
│       │   ├── model_router.py     # Task→model routing rules
│       │   └── feedback.py         # Feedback loop controllers
│       ├── agents/
│       │   ├── __init__.py
│       │   ├── base.py             # Base agent class
│       │   ├── query_planner.py    # Agent 1: GPT-5.4, research planning
│       │   ├── paper_triage.py     # Agent 2: Gemini, batch paper screening
│       │   ├── deep_reader.py      # Agent 3: Claude Opus/Sonnet, paper analysis
│       │   ├── critique.py         # Agent 4: Claude Opus, critical analysis
│       │   ├── gap_detector.py     # Agent 5: GPT-5.4, research gap detection
│       │   ├── verification.py     # Agent 6: Claude Sonnet, gap verification
│       │   ├── idea_generator.py   # Agent 7: GPT-5.4, idea generation
│       │   └── experiment_planner.py # Agent 8: GPT-5.4, experiment design
│       ├── services/
│       │   ├── __init__.py
│       │   ├── llm_client.py       # LiteLLM unified wrapper + cost tracking
│       │   ├── paper_search.py     # Semantic Scholar + arXiv + OpenAlex APIs
│       │   ├── pdf_parser.py       # PyMuPDF-based PDF extraction
│       │   └── embedding.py        # OpenAI embedding service
│       ├── storage/
│       │   ├── __init__.py
│       │   ├── database.py         # PostgreSQL (SQLAlchemy async)
│       │   ├── models.py           # DB models (papers, sessions)
│       │   ├── vector_store.py     # Qdrant client (Phase 2)
│       │   ├── graph_store.py      # Neo4j client (Phase 3)
│       │   └── session_memory.py   # Redis session state
│       └── cost/
│           ├── __init__.py
│           └── tracker.py          # Per-call and per-session cost tracking
├── tests/
│   ├── __init__.py
│   ├── test_agents/
│   ├── test_services/
│   └── test_api/
└── scripts/
    └── seed_data.py                # Dev helper scripts
```

---

## Phase 1: MVP (Core Pipeline) — Steps

### Step 1: Project Foundation
- [x] Create `pyproject.toml` with dependencies: fastapi, uvicorn, litellm, sqlalchemy[asyncio], asyncpg, redis, httpx, pydantic, python-dotenv, pymupdf
- [x] Create `.env.example` with placeholders for OPENAI_API_KEY, GOOGLE_API_KEY, ANTHROPIC_API_KEY, DATABASE_URL, REDIS_URL
- [x] Create `docker-compose.yml` for PostgreSQL + Redis
- [x] Create base package structure (`src/science_ai/`)

### Step 2: Configuration & LLM Client
- [x] `config.py` — Pydantic Settings loading env vars, model pricing table, routing rules
- [x] `llm_client.py` — LiteLLM wrapper with: unified call interface, reasoning_effort parameter support, cost tracking per call, retry logic, prompt caching headers

### Step 3: Cost Tracker
- [x] `cost/tracker.py` — Record each API call (agent, model, tokens, cost), session cost summaries, per-model breakdowns

### Step 4: Paper Search Services
- [x] `paper_search.py` — Semantic Scholar API client (search, paper details, citations), arXiv API client (search by query), unified search interface returning standardized paper metadata

### Step 5: Storage Layer (PostgreSQL)
- [x] `storage/database.py` — Async SQLAlchemy engine + session factory
- [x] `storage/models.py` — Papers table, ResearchSessions table (matching the SQL schema in the architecture doc)
- [x] `storage/session_memory.py` — Redis client for session state (plan, queue, results, cost)

### Step 6: Base Agent Framework
- [x] `agents/base.py` — BaseAgent class with: model selection, LLM client injection, structured output parsing, cost tracking integration, standard input/output contracts

### Step 7: Agent 1 — Query Planner
- [x] `agents/query_planner.py` — Takes natural language research question, decomposes into sub-questions, generates search keywords, calls paper search APIs, returns structured research plan (JSON schema from architecture doc)

### Step 8: Agent 2 — Paper Triage
- [x] `agents/paper_triage.py` — Takes batch of paper title+abstract, scores relevance (0-1), categorizes (survey/method/application/benchmark/theory), marks priority (must_read/worth_reading/skip), processes in batches of 50-100

### Step 9: Agent 3 — Deep Reader
- [x] `agents/deep_reader.py` — Takes single paper full text (or multiple for comparison), extracts full Paper Knowledge Object (research_problem, method, assumptions, experiments, limitations, future_work, key_evidence), uses Opus for high-priority, Sonnet for medium

### Step 10: Orchestrator (Phase 1 Pipeline)
- [x] `orchestrator/orchestrator.py` — Chains: Query Planner → Paper Search → Paper Triage → Deep Reader, manages paper queue and status transitions, tracks costs across the pipeline
- [x] `orchestrator/model_router.py` — Rules engine mapping task type → model + reasoning_effort

### Step 11: FastAPI Endpoints
- [x] `api/schemas.py` — Request/response Pydantic models
- [x] `api/routes.py` — POST /research/start (submit question, get session_id), GET /research/{session_id}/status, GET /research/{session_id}/results
- [x] `main.py` — FastAPI app with router registration

### Step 12: Integration & Testing
- [x] Wire everything together in main.py
- [x] Add basic tests for each agent (mock LLM calls)
- [x] Add integration test for full Phase 1 pipeline

---

## Phase 2: Deep Analysis (Later)
- Add Critique Agent (Agent 4) + Verification Agent (Agent 6)
- Add Qdrant vector store + embedding service
- Implement Gap Detection mechanisms A (method-problem matrix) and D (evaluation blind spots)
- Implement feedback loop 1 (search refinement)

## Phase 3: Idea Generation (Later)
- Add Neo4j knowledge graph
- Add Gap Detector (Agent 5), Idea Generator (Agent 7), Experiment Planner (Agent 8)
- Implement all 3 feedback loops
- Add Report Writer

## Phase 4: Scale & Optimize (Later)
- Prompt caching optimization
- Batch API integration
- Web Dashboard (Next.js)
- Cross-session knowledge accumulation
- Cost optimization and monitoring dashboard

---

## Phase 5: Real Mode + Settings Page (CURRENT)

### Goal
Replace all demo/mock data with real backend calls. Add a Settings page for API keys + Zotero credentials. Integrate Zotero as both a paper source (read) and output destination (write).

---

### Step 1: Backend — Settings API Endpoints
**Files:** `src/science_ai/api/routes.py`, `src/science_ai/api/schemas.py`, `src/science_ai/config.py`

Add Zotero fields to `Settings`:
```python
zotero_library_id: str = ""
zotero_api_key: str = ""
zotero_library_type: str = "user"  # "user" or "group"
```

Add three new endpoints:
- `GET /api/v1/settings` — Return current API key status (masked, e.g. `sk-...abc`), Zotero config, and budget. Never expose full keys.
- `PUT /api/v1/settings` — Accept API keys + Zotero creds + config, write to `.env` file, hot-reload `settings` singleton.
- `POST /api/v1/settings/test` — Test connectivity per provider (LLM keys + Zotero), return success/failure per key.

Keys persist to `.env` so they survive server restarts.

### Step 2: Backend — List Sessions Endpoint
**File:** `src/science_ai/api/routes.py`

Add:
- `GET /api/v1/sessions` — Return all sessions from in-memory `_sessions` dict (id, status, question, cost). Replaces hardcoded demo session list.

### Step 3: Frontend — API Client Extensions
**File:** `dashboard/src/lib/api.ts`

Add TypeScript interfaces and api methods:
- `api.getSettings()` → `GET /settings`
- `api.updateSettings(data)` → `PUT /settings`
- `api.testSettings()` → `POST /settings/test`
- `api.listSessions()` → `GET /sessions`

### Step 4: Frontend — Settings Page (NEW)
**File:** `dashboard/src/app/settings/page.tsx` (new file)

Build settings page with sections:

**LLM API Keys section:**
- Input fields for OpenAI, Anthropic, Google API keys (password-masked, show last 4 chars when saved)
- "Test Connection" button per provider — green check or red X

**Zotero section:**
- Zotero Library ID input
- Zotero API Key input (password-masked)
- Library type toggle: "User" / "Group"
- "Test Connection" button — verifies access to the Zotero library
- Optional: select Zotero collection to read from / write to

**General section:**
- Cost budget input field
- "Save All" button — calls `PUT /settings`

Uses existing glass UI style (GlassCard, glass-input, glass-btn).

### Step 5: Frontend — Add Settings to Sidebar
**File:** `dashboard/src/components/Sidebar.tsx`

Add "Settings" nav item with gear icon, linking to `/settings`.

### Step 6: Frontend — Remove Demo Data, Wire to Real API

**Dashboard** (`dashboard/src/app/page.tsx`):
- Remove `DEMO_SESSIONS` constant
- Call `api.listSessions()` on mount to fetch real sessions
- Show empty state when no sessions ("No sessions yet — start your first research")
- Show warning banner when API keys not configured (link to /settings)

**Session page** (`dashboard/src/app/session/page.tsx`):
- Remove `DEMO_RESULT` constant
- Remove `if (sessionId.startsWith("demo"))` fallback
- Show proper error/loading states for real API responses
- Add auto-refresh polling when status is "running"

**Costs page** (`dashboard/src/app/costs/page.tsx`):
- Remove `DEMO_COST_DATA`
- Aggregate real cost data from sessions via `api.listSessions()` + `api.getCost()`
- Show empty state when no data

### Step 7: Frontend — API Key Warning on New Research
**File:** `dashboard/src/app/new/page.tsx`

Before the form, check settings. If no API keys configured, show warning banner: "Configure your API keys in Settings before starting research."

### Step 8: Backend — Zotero Service (READ)
**File:** `src/science_ai/services/zotero_client.py` (new)

Create `ZoteroClient` using the `pyzotero` library:
- `search(query, limit)` → fetch items matching a query, return `PaperMeta` objects
- `get_collection_items(collection_id)` → fetch all items in a Zotero collection
- `get_all_items(limit)` → fetch top-level library items
- Map Zotero item fields → `PaperMeta` (title, authors, year, abstract, DOI, URL)
- Fetch PDF attachments and extract full text via existing `pdf_parser.py`

Integrate into `PaperSearchService`:
- Add `"zotero"` as a new source option
- When user selects Zotero source, query their library instead of (or in addition to) Semantic Scholar / arXiv

### Step 9: Backend — Zotero Service (WRITE)
**File:** `src/science_ai/services/zotero_client.py` (extend)

Add write methods:
- `create_collection(name)` → create a new Zotero collection for the research session
- `add_item(paper_meta)` → create a Zotero item from a PaperMeta
- `add_note(item_key, content)` → attach a note (knowledge object, critique, or gap analysis) to a Zotero item
- `add_tags(item_key, tags)` → tag items with status (e.g. "must_read", "gap_source", "ScienceAI")

**File:** `src/science_ai/orchestrator/orchestrator.py` (extend)

Hook Zotero export into the pipeline:
- After Phase 1: Export triaged papers to a Zotero collection, tag by priority
- After Phase 2: Attach critique + gap notes to relevant Zotero items
- After Phase 3: Attach final report as a standalone Zotero note, tag idea-source papers

### Step 10: Frontend — Zotero Source Option on New Research
**File:** `dashboard/src/app/new/page.tsx`

Add a "Paper Source" selector:
- Options: "Web Search" (Semantic Scholar + arXiv, default), "Zotero Library", "Both"
- When "Zotero" selected, optionally show a collection picker (fetched from API)
- Pass source preference to `api.startResearch()`

**File:** `src/science_ai/api/schemas.py`

Add `source` field to `StartResearchRequest`: `"web"`, `"zotero"`, or `"both"`.

---

### Files Changed Summary

| File | Action |
|------|--------|
| `src/science_ai/config.py` | Add Zotero settings fields |
| `src/science_ai/api/schemas.py` | Add settings, sessions, Zotero schemas |
| `src/science_ai/api/routes.py` | Add settings + sessions + Zotero endpoints |
| `src/science_ai/services/zotero_client.py` | **New** — Zotero read/write via pyzotero |
| `src/science_ai/services/paper_search.py` | Add Zotero as paper source |
| `src/science_ai/orchestrator/orchestrator.py` | Hook Zotero export after each phase |
| `dashboard/src/lib/api.ts` | Add settings + sessions + Zotero API methods |
| `dashboard/src/app/settings/page.tsx` | **New** — settings page (LLM keys + Zotero) |
| `dashboard/src/components/Sidebar.tsx` | Add settings nav item |
| `dashboard/src/app/page.tsx` | Replace demo with real sessions |
| `dashboard/src/app/session/page.tsx` | Remove demo fallback, add polling |
| `dashboard/src/app/costs/page.tsx` | Replace demo with real cost data |
| `dashboard/src/app/new/page.tsx` | Add API key warning + Zotero source picker |
| `pyproject.toml` | Add `pyzotero` dependency |
