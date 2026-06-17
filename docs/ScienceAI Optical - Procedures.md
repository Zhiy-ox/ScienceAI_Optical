---
title: ScienceAI Optical — Procedures
aliases:
  - ScienceAI Setup
  - ScienceAI Procedures
  - Optical Research Pipeline
tags:
  - project/scienceai
  - type/procedure
  - tool/ai
  - research/optical
created: 2026-06-17
---

# 🔬 ScienceAI Optical — Procedures

> [!abstract] What this is
> An AI-driven scientific literature review system. You give it a research question; it **searches → triages → deep-reads → critiques → detects gaps → generates ideas → plans experiments → writes a report**, streaming progress live with optional human approval gates.

> [!info] Quick links
> - Dashboard → `http://localhost:3000`
> - API docs (Swagger) → `http://localhost:8000/docs`
> - Health check → `http://localhost:8000/health`

---

## 🗺️ Map of contents

- [[#✅ Prerequisites]]
- [[#📦 Procedure 1 — Install]]
- [[#⚙️ Procedure 2 — Configure]]
- [[#🚀 Procedure 3 — Launch]]
- [[#🧪 Procedure 4 — Run a Research Session]]
- [[#🔎 Procedure 5 — Read the Results]]
- [[#🛑 Procedure 6 — Shut Down]]
- [[#🧩 Reference — Pipeline Stages]]
- [[#🆘 Troubleshooting]]

---

## ✅ Prerequisites

> [!check] Before you start, confirm you have:
> - [ ] **Python 3.11+** (`python3 --version`)
> - [ ] **Node.js 18+** (`node --version`)
> - [ ] **Docker Desktop** running (`docker ps`)
> - [ ] One LLM provider — **either** an API key (OpenAI / Anthropic / Google) **or** local CLI tools (`claude`, `codex`, `agy`) for free mode

---

## 📦 Procedure 1 — Install

> [!example]+ Steps
> ```bash
> # 1. Clone
> git clone https://github.com/Zhiy-ox/ScienceAI_Optical.git
> cd ScienceAI_Optical
>
> # 2. Python environment (keeps everything in ./venv)
> python3.12 -m venv venv          # any 3.11+ interpreter
> source venv/bin/activate          # Windows: venv\Scripts\activate
> python -m pip install --upgrade pip
> pip install -e ".[dev]"
>
> # 3. Dashboard
> cd dashboard && npm install && cd ..
> ```

> [!warning] Python version matters
> If `pip install` says **"requires Python >=3.11"**, your venv was built with an older interpreter. Delete and recreate it:
> ```bash
> deactivate; rm -rf venv
> python3.12 -m venv venv && source venv/bin/activate
> ```

> [!tip] Using conda instead?
> ```bash
> conda create -n scienceai python=3.12 -y
> conda activate scienceai
> pip install -e ".[dev]"
> ```

---

## ⚙️ Procedure 2 — Configure

> [!example]+ Create the env file
> ```bash
> cp .env.example .env
> ```

Edit `.env` and set **at minimum** the LLM backend:

| Variable | Purpose | Default |
|----------|---------|---------|
| `LLM_BACKEND` | `cli` (free, local tools) or `api` (paid keys) | `cli` |
| `OPENAI_API_KEY` | API mode + embeddings | — |
| `ANTHROPIC_API_KEY` | API mode (optional) | — |
| `GOOGLE_API_KEY` | API mode (optional) | — |
| `CHECKPOINTER_DSN` | Postgres DSN for durable, resumable runs | empty = in-memory |
| `FANOUT_CONCURRENCY` | Parallel agent calls per fan-out stage | `5` |
| `COST_BUDGET_USD` | Optional per-session spend cap | `10.0` |

> [!note] CLI vs API mode
> - **CLI mode** = `$0.00`, needs `claude`/`codex`/`agy` in your PATH. **Best for testing.**
> - **API mode** = pay-per-token, needs a key. **Best for production.**

---

## 🚀 Procedure 3 — Launch

> [!example]+ Start the databases (always first)
> ```bash
> docker-compose up -d
> ```
> Starts **PostgreSQL** (`:5432`, sessions) and **Qdrant** (`:6333`, vectors).

### Option A — One command (macOS)

```bash
./start.sh
```

> [!success] What `start.sh` does
> Brings up Docker, opens a Terminal for the **backend**, opens a Terminal for the **dashboard**, and prints the access URLs.

### Option B — Manual (any OS)

> [!example]+ Two terminals
> **Terminal 1 — Backend**
> ```bash
> source venv/bin/activate
> python -m uvicorn science_ai.main:app --reload --port 8000
> ```
> **Terminal 2 — Dashboard**
> ```bash
> cd dashboard
> npm run dev
> ```

> [!check] Verify it's up
> - [ ] `http://localhost:8000/health` returns `{"status":"ok"}`
> - [ ] `http://localhost:3000` loads with a **green** connection dot

---

## 🧪 Procedure 4 — Run a Research Session

> [!check] Walkthrough
> 1. [ ] **Settings** (`/settings`) → paste an API key → **Save** → **Test** _(skip if using CLI mode)_
> 2. [ ] **New Research** (`/new`) → type a question, or click an example prompt
> 3. [ ] Pick a **Paper Source**: Web · Zotero · Both
> 4. [ ] Pick a **Phase**:
>     - **Phase 1** — Search + Triage + Deep Read _(~5 min)_
>     - **Phase 2** — + Critique + Gaps + Verify _(~10 min)_
>     - **Phase 3** — + Ideas + Experiments + Report _(~20 min)_
> 5. [ ] _(Optional)_ Enable **Approval Gates** to pause for review
> 6. [ ] Set **Max Papers** (default 15)
> 7. [ ] Click **Start Research Pipeline**

> [!tip] Approval gates (human-in-the-loop)
> When the pipeline pauses, a card appears:
> - **Approve** → continue
> - **Edit** → tweak the plan/gaps, then approve
> - **Reject** → stop the run

> [!info] What you'll see live
> A stage rail showing the active node, a streaming event log (SSE), and a running cost counter.

---

## 🔎 Procedure 5 — Read the Results

When the run completes, the session page has six tabs:

| Tab | Contents |
|-----|----------|
| **Overview** | Plan, metadata, cost breakdown |
| **Papers** | Triaged papers + deep-read summaries |
| **Gaps** | Verified gaps with mechanism + evidence |
| **Ideas** | Ideas with strategy, feasibility, experiment plan |
| **Report** | Full structured report with citations |
| **Trace** | Per-node execution timing |

> [!tip] Performance inspection
> The **Debug** page (`/debug`) → **Pipeline Inspector** shows total time, the slowest node, a time-share chart, and an execution-order timeline.

---

## 🛑 Procedure 6 — Shut Down

> [!example]+ Stop everything
> ```bash
> ./stop.sh            # macOS: stops Docker + backend + dashboard
> ```
> Or manually:
> ```bash
> docker-compose down  # stop databases
> # Ctrl-C in each terminal to stop backend + dashboard
> ```

---

## 🧩 Reference — Pipeline Stages

> [!note]- Expand: all 12 nodes
> | # | Node | Phase | Does |
> |---|------|-------|------|
> | 1 | `plan` | 1+ | Question → search queries |
> | 2 | `plan_gate` | 1+ | Optional plan approval |
> | 3 | `search` | 1+ | Semantic Scholar / arXiv / Zotero |
> | 4 | `triage` | 1+ | Relevance scoring |
> | 5 | `select_papers` | 1+ | Pick top papers |
> | 6 | `deep_read_one` | 1+ | Parallel → Knowledge Objects |
> | 7 | `critique_one` | 2+ | Parallel → methodology critique |
> | 8 | `gap_detect` | 2+ | 4-mechanism gap synthesis |
> | 9 | `verify` | 2+ | Verify gap novelty |
> | 10 | `idea` | 3 | Generate ideas from gaps |
> | 11 | `experiment` | 3 | Plan experiments |
> | 12 | `report` | 3 | Write final report |

> [!note]- Expand: feedback loops & gap mechanisms
> **Feedback loops** (max 2 iterations each):
> - **Loop 1** — refine search with newly discovered keywords
> - **Loop 2** — re-detect gaps when verification rate is low
> - **Loop 3** — regenerate ideas when feasibility is low
>
> **Gap mechanisms:**
> - A) Method-Problem Matrix — unstudied combinations
> - B) Assumption Chain — shared untested assumptions
> - C) Citation Graph — isolated clusters
> - D) Evaluation Blind Spots — untested metrics/datasets

---

## 🆘 Troubleshooting

> [!failure]- `pip install` → "requires Python >=3.11"
> The venv uses an old interpreter. Recreate with `python3.12 -m venv venv`.

> [!failure]- Dashboard shows "Offline mode"
> Backend isn't running. Start it: `uvicorn science_ai.main:app --port 8000`.

> [!failure]- "No API keys configured"
> Add a key in **Settings**, or set `LLM_BACKEND=cli` in `.env`.

> [!failure]- Phase 3 returns no ideas
> Pull the latest code — ideation now falls back to candidate gaps when none are strictly verified.

> [!failure]- Debug page → 404
> Pull the latest code — the old `/progress` endpoint was replaced by `/trace`.

> [!failure]- Docker services won't start
> Make sure Docker Desktop is running (`docker ps`).

---

## 🔗 Related

- API reference & full project docs → see `README.md` in the repo root
- Interactive API explorer → `http://localhost:8000/docs`
