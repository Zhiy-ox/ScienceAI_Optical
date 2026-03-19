# ScienceAI_Optical

AI-driven research assistant that automates literature review, gap detection, and idea generation for scientific research — with a focus on optical science.

## Features

- **Multi-model orchestration** — routes tasks to GPT-5.4, Gemini 3.1 Pro, and Claude Opus/Sonnet 4.6 based on capability fit
- **Dual LLM backend** — paid API mode (via litellm) or free CLI mode (local CLI tools)
- **8 specialized agents** — query planning, paper triage, deep reading, critique, gap detection, verification, idea generation, experiment planning
- **Feedback loops** — downstream results can correct upstream decisions (search refinement, gap re-verification, idea feasibility checks)
- **Knowledge storage** — PostgreSQL, Qdrant vector index, Redis session memory
- **Zotero integration** — import/export papers from your Zotero library
- **Web dashboard** — Next.js app with liquid glass UI at `localhost:3000`

## Prerequisites

- Python 3.11+
- Node.js 18+ and npm
- Docker Desktop (for PostgreSQL, Redis, Qdrant)

## Quick Start

```bash
# Clone and enter the project
git clone https://github.com/Zhiy-ox/ScienceAI_Optical.git
cd ScienceAI_Optical

# Create and activate a virtual environment
python -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install -e ".[dev]"

# Install dashboard dependencies
cd dashboard && npm install && cd ..

# Copy and edit environment config
cp .env.example .env  # then fill in your API keys

# Start all services
./start.sh
```

### CLI Mode (Free)

To use the free CLI backend instead of paid APIs, install the three CLI tools:

```bash
npm install -g @anthropic-ai/claude-code   # claude
npm install -g @openai/codex               # codex
npm install -g @google/gemini-cli           # gemini
```

Then set **CLI Mode** in the Settings page (`localhost:3000/settings`) or set `LLM_BACKEND=cli` in your `.env`.

## Architecture

See [ScienceAI_Architecture_v2.md](ScienceAI_Architecture_v2.md) for the full system design, model routing tables, cost estimates, and implementation phases.

## Scripts

See [README_SCRIPTS.md](README_SCRIPTS.md) for details on `start.sh` and `stop.sh`.
