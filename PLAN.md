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
