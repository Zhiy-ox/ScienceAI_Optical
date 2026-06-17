# ScienceAI Optical

AI-driven scientific literature review system. Give it a research question, and it searches, triages, deep-reads, critiques, detects gaps, generates ideas, plans experiments, and writes a full research report — with live progress streaming and optional human-in-the-loop approval gates.

---

## Architecture Overview

```
┌──────────────────────────────────────────────────┐
│  Next.js Dashboard (localhost:3000)               │
│  Glass-morphism UI · SSE live streaming           │
└──────────────┬───────────────────────────────────┘
               │  REST + SSE
┌──────────────▼───────────────────────────────────┐
│  FastAPI Backend (localhost:8000)                  │
│  /api/v1/research/start · /stream · /resume       │
└──────────────┬───────────────────────────────────┘
               │
┌──────────────▼───────────────────────────────────┐
│  LangGraph StateGraph Pipeline                    │
│  12 nodes · 3 feedback loops · 2 HITL gates       │
│  Checkpointed via Postgres or MemorySaver         │
└──────┬──────────┬────────────┬───────────────────┘
       │          │            │
  PostgreSQL    Qdrant     LLM Provider
  (sessions)   (vectors)  (API or CLI)
```

---

## Pipeline Stages

The pipeline runs up to 12 nodes depending on the chosen phase:

| #  | Node              | Phase | What it does                                    |
|----|-------------------|-------|-------------------------------------------------|
| 1  | `plan`            | 1+    | Decomposes the question into search queries     |
| 2  | `plan_gate`       | 1+    | Optional HITL approval of the search plan       |
| 3  | `search`          | 1+    | Searches Semantic Scholar, arXiv, Zotero        |
| 4  | `triage`          | 1+    | Scores papers for relevance (must/worth/skip)   |
| 5  | `select_papers`   | 1+    | Picks top papers within the budget              |
| 6  | `deep_read_one`   | 1+    | Parallel fan-out: extracts Knowledge Objects    |
| 7  | `critique_one`    | 2+    | Parallel fan-out: critiques each paper          |
| 8  | `gap_detect`      | 2+    | 4-mechanism gap detection (see below)           |
| 9  | `verify`          | 2+    | Verifies gap novelty via targeted search        |
| 10 | `idea`            | 3     | Generates research ideas from gaps              |
| 11 | `experiment`      | 3     | Plans experiments for each idea                 |
| 12 | `report`          | 3     | Writes the final research report                |

**Feedback loops** (bounded, max 2 iterations each):
- **Loop 1** (after deep read): refine search with newly discovered keywords
- **Loop 2** (after verification): re-detect gaps when verification rate is low
- **Loop 3** (after experiments): regenerate ideas when feasibility is low

**Gap detection mechanisms:**
- A) Method-Problem Matrix — empty cells = unstudied combinations
- B) Assumption Chain Analysis — shared untested assumptions
- C) Citation Graph Structural Analysis — isolated clusters
- D) Evaluation Blind Spots — metrics/datasets never tested

---

## Prerequisites

- **Python 3.11+**
- **Node.js 18+**
- **Docker Desktop** (for PostgreSQL and Qdrant)
- At least one LLM provider: an API key (OpenAI/Anthropic/Google) or local CLI tools (`claude`, `codex`, `agy`) for free mode

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/Zhiy-ox/ScienceAI_Optical.git
cd ScienceAI_Optical
```

### 2. Create a Python virtual environment

```bash
python3.12 -m venv venv          # use any 3.11+ interpreter
source venv/bin/activate          # Windows: venv\Scripts\activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

> If you use conda: `conda create -n scienceai python=3.12 -y && conda activate scienceai && pip install -e ".[dev]"`

### 3. Install the dashboard

```bash
cd dashboard && npm install && cd ..
```

### 4. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` with your settings. The minimum is choosing an LLM backend:

| Variable | Description |
|----------|-------------|
| `LLM_BACKEND` | `cli` (free, uses local CLI tools) or `api` (paid, uses API keys) |
| `OPENAI_API_KEY` | OpenAI API key (for API mode and embeddings) |
| `ANTHROPIC_API_KEY` | Anthropic API key (optional, for API mode) |
| `GOOGLE_API_KEY` | Google AI API key (optional, for API mode) |
| `CHECKPOINTER_DSN` | Postgres DSN for durable checkpoints. Leave empty for in-memory |
| `FANOUT_CONCURRENCY` | Max parallel agent calls per fan-out stage (default: 5) |
| `COST_BUDGET_USD` | Optional cost limit per session |

### 5. Start the database services

```bash
docker-compose up -d
```

This starts:
- **PostgreSQL 16** on port 5432 (session storage + optional checkpointing)
- **Qdrant v1.12** on port 6333 (vector embeddings for gap detection)

---

## Running

### Option A: One command (macOS)

```bash
./start.sh
```

This launches Docker services, the FastAPI backend, and the Next.js dashboard in separate Terminal windows.

To stop everything:

```bash
./stop.sh
```

### Option B: Manual (any OS)

**Terminal 1 — Backend:**
```bash
source venv/bin/activate
python -m uvicorn science_ai.main:app --reload --port 8000
```

**Terminal 2 — Dashboard:**
```bash
cd dashboard
npm run dev
```

### Access points

| Service | URL |
|---------|-----|
| Dashboard | `http://localhost:3000` |
| API health check | `http://localhost:8000/health` |
| Swagger API docs | `http://localhost:8000/docs` |
| PostgreSQL | `localhost:5432` |
| Qdrant | `localhost:6333` |

---

## Usage Walkthrough

### Step 1 — Configure API Keys

Open **Settings** (`http://localhost:3000/settings`). Paste at least one API key and click **Save**. The test button verifies connectivity.

If using CLI mode (`LLM_BACKEND=cli`), you need `claude`, `codex`, or `agy` available in your PATH. No API key required.

### Step 2 — Start a Research Session

Navigate to **New Research** (`http://localhost:3000/new`):

1. **Type your research question** — or click one of the example prompts
2. **Choose a paper source**: Web Search, Zotero Library, or Both
3. **Select the pipeline phase**:
   - **Phase 1** — Search + Triage + Deep Read (~5 min)
   - **Phase 2** — + Critique + Gap Detection + Verification (~10 min)
   - **Phase 3** — + Ideas + Experiments + Report (~20 min)
4. **Optional: enable approval gates** — pause at the search plan or gap list for your review before continuing
5. **Set max papers** (default 15, range 5-50)
6. Click **Start Research Pipeline**

### Step 3 — Monitor Live Progress

The session page opens automatically and shows:
- **Stage progress rail** — which of the 12 nodes is active
- **Live event stream** — real-time SSE updates from each node
- **Cost counter** — running token cost (updates per stage)

### Step 4 — Approval Gates (if enabled)

When the pipeline pauses at a gate, a card appears showing the plan or gap list:
- **Approve** — continue the pipeline
- **Edit** — modify the plan/gaps, then approve
- **Reject** — stop the pipeline

### Step 5 — Explore Results

Once complete, the session has six tabs:

| Tab | What it shows |
|-----|---------------|
| **Overview** | Research plan, session metadata, cost breakdown |
| **Papers** | Triaged papers with relevance scores and deep-read summaries |
| **Gaps** | Verified research gaps with detection mechanism and evidence |
| **Ideas** | Generated ideas with strategy, feasibility, and experiment plans |
| **Report** | Full structured research report with citations |
| **Trace** | Per-node execution timing (for debugging performance) |

### Step 6 — Pipeline Inspector

The **Debug** page (`http://localhost:3000/debug`) shows:
- Summary metrics (node runs, total time, slowest node)
- Time-share bar chart per node
- Execution-order timeline with per-node durations

---

## Zotero Integration (Optional)

1. Go to **Settings** and enter your **Zotero Library ID** and **Zotero API Key**
2. On the New Research page, set **Paper Source** to "Zotero Library" or "Both"
3. Your Zotero collections appear as badges so you can see what's available
4. After a run, results are automatically exported back to your Zotero library

---

## Project Structure

```
ScienceAI_Optical/
├── src/science_ai/
│   ├── agents/                    # LLM-powered agents (one per pipeline stage)
│   │   ├── gap_detection/         # 4 gap-detection mechanisms
│   │   ├── query_planner.py       # Stage 1: decompose question into search queries
│   │   ├── paper_triage.py        # Stage 3: score papers for relevance
│   │   ├── deep_reader.py         # Stage 5: extract Knowledge Objects
│   │   ├── critique.py            # Stage 6: critique paper methodology
│   │   ├── gap_detector.py        # Stage 8: synthesize gaps from 4 mechanisms
│   │   ├── verification.py        # Stage 9: verify gap novelty
│   │   ├── idea_generator.py      # Stage 10: generate research ideas
│   │   ├── experiment_planner.py  # Stage 11: design experiments
│   │   └── report_writer.py       # Stage 12: write final report
│   ├── orchestrator/graph/        # LangGraph pipeline
│   │   ├── builder.py             # Graph topology (nodes + edges)
│   │   ├── nodes.py               # Node functions wrapping agents
│   │   ├── edges.py               # Conditional routers (phase exit, loops)
│   │   ├── state.py               # ResearchState TypedDict with reducers
│   │   ├── runner.py              # High-level runner (singleton)
│   │   └── checkpointer.py        # Postgres / MemorySaver setup
│   ├── api/
│   │   ├── routes.py              # FastAPI endpoints + SSE streaming
│   │   └── schemas.py             # Pydantic request/response models
│   ├── services/
│   │   ├── llm_client.py          # API-mode LLM client (litellm)
│   │   ├── cli_llm_client.py      # CLI-mode LLM client (subprocess)
│   │   ├── paper_search.py        # Semantic Scholar + arXiv search
│   │   └── embedding.py           # OpenAI embedding service
│   ├── storage/
│   │   ├── database.py            # SQLAlchemy async engine
│   │   ├── session_repo.py        # Session CRUD
│   │   ├── vector_store.py        # Qdrant vector operations
│   │   └── graph_store.py         # In-memory citation graph
│   ├── cost/tracker.py            # Per-session cost tracking
│   └── config.py                  # Pydantic settings from .env
├── dashboard/                     # Next.js App Router frontend
│   └── src/
│       ├── app/                   # Pages: /, /new, /session, /debug, /settings, /costs
│       ├── components/            # GlassCard, PipelineProgress
│       └── lib/api.ts             # Typed API client + SSE streaming
├── tests/                         # pytest suite (159 tests)
├── docker-compose.yml             # PostgreSQL + Qdrant
├── start.sh / stop.sh             # macOS convenience scripts
└── .env.example                   # Environment variable template
```

---

## Testing

```bash
source venv/bin/activate
pytest tests/ -v                   # full suite
pytest tests/test_graph/ -v        # pipeline tests only
ruff check src/ tests/             # linter
```

```bash
cd dashboard
npm run build                      # type-check + build
```

---

## CLI vs API Mode

| | CLI Mode (`LLM_BACKEND=cli`) | API Mode (`LLM_BACKEND=api`) |
|---|---|---|
| **Cost** | Free ($0.00) | Pay per token |
| **Requirements** | `claude` / `codex` / `agy` in PATH | API key in `.env` |
| **Speed** | Slower (subprocess per call) | Faster (HTTP API) |
| **Task routing** | Planning -> codex, Triage -> agy, Deep read -> claude | All -> litellm (auto-routes to provider) |
| **JSON reliability** | Needs robust parsing (bare arrays, markdown blocks) | Native JSON mode |

CLI mode is the default and ideal for testing without any billing. Switch to API mode for production runs by setting `LLM_BACKEND=api` in `.env`.

---

## API Quick Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/research/start` | Start a research session |
| `GET` | `/api/v1/research/{id}/stream` | SSE live progress stream |
| `GET` | `/api/v1/research/{id}/status` | Session status + HITL interrupt |
| `POST` | `/api/v1/research/{id}/resume` | Resume after HITL approval |
| `GET` | `/api/v1/research/{id}/results` | Full results (after completion) |
| `GET` | `/api/v1/research/{id}/trace` | Per-node execution timing |
| `GET` | `/api/v1/research/{id}/cost` | Detailed cost breakdown |
| `GET` | `/api/v1/sessions` | List all sessions |
| `GET` | `/api/v1/settings` | Current settings (masked keys) |
| `PUT` | `/api/v1/settings` | Update settings |
| `POST` | `/api/v1/settings/test` | Test API key connectivity |
| `GET` | `/api/v1/zotero/collections` | List Zotero collections |

Full interactive docs at `http://localhost:8000/docs`.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `pip install` fails with "requires Python >=3.11" | Recreate venv with `python3.12 -m venv venv` |
| Dashboard shows "Offline mode" | Start the backend: `uvicorn science_ai.main:app --port 8000` |
| "No API keys configured" warning | Go to Settings and add at least one key, or set `LLM_BACKEND=cli` |
| Phase 3 produces no ideas | Pull the latest code (fixed: ideation now falls back to candidate gaps) |
| Debug page shows 404 | Pull the latest code (the old `/progress` endpoint was replaced by `/trace`) |
| Docker services won't start | Ensure Docker Desktop is running: `docker ps` |
| `CHECKPOINTER_DSN` errors | Leave it empty for in-memory mode, or ensure Postgres is running |
